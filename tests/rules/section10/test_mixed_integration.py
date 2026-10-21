"""10.06 native physical model ownership through targeting and public declarations."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import geometry, scenario
from tests.support.section04_fixtures import choose, finish_attacks, pending, weapon_rows
from tests.support.section10_fixtures import LORD, WRAITHLORD, accepted_pools, assert_valid, submit
from tests.support.section10_mixed import mixed_case
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetViolationCode,
    shooting_target_candidate_for_model,
)
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("physical", ["monster", "infantry"])
@pytest.mark.parametrize("target", ["engaged", "outside"])
def test_native_mixed_target_producer_keeps_physical_keywords(
    section10_definitions: Section02Definitions, physical: str, target: str
) -> None:
    d = section10_definitions
    session, state, body, leader, formation = mixed_case(d)
    view = rules_unit_view_by_id(state=state, unit_instance_id=formation.attached_unit_instance_id)
    assert "MONSTER" in view.keywords
    assert "MONSTER" not in leader.own_models[0].keywords
    unit = body if physical == "monster" else leader
    suffix = "shuriken-catapult" if physical == "monster" else "bolt-pistol"
    target_id = "enemy:target" if target == "engaged" else "enemy:outside"
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=unit,
        attacker_model_instance_id=unit.own_model_ids()[0],
        weapon_profile=d.weapon(f"{unit.datasheet_id}:{suffix}"),
        target_unit_id=target_id,
    )
    valid = physical == "monster" or target == "engaged"
    assert result.is_legal is valid
    assert result.observer_model_id == unit.own_model_ids()[0]
    assert result.target_visible_model_ids
    assert result.line_of_sight_witness is not None
    if valid:
        assert result.hit_roll_modifier == (-1 if physical == "monster" else 0)
        assert result.violation_code is None
    else:
        assert result.violation_code is ShootingTargetViolationCode.LOCKED_IN_COMBAT
    assert pending(session).decision_type == "select_shooting_unit"


def test_mixed_public_declaration_rejects_infantry_outside_then_resolves_legal_split(
    section10_definitions: Section02Definitions,
) -> None:
    session, state, body, leader, formation = mixed_case(section10_definitions)
    # Native shapes are non-overlapping and coherent; opposite-side target rays
    # avoid the intervening model geometry of the retained expensive pilot.
    a = geometry(body, (Pose.at(10, 10),))[0]
    b = geometry(leader, (Pose.at(10, 13.4),))[0]
    assert not a.base_overlaps(b)
    assert a.base_distance_to(b) < 2
    choose(session, pending(session), formation.attached_unit_instance_id)
    assert {o.option_id for o in pending(session).options} == {"close_quarters"}
    choose(session, pending(session), "close_quarters")
    request = pending(session)
    assert request.decision_type == "submit_shooting_declaration"
    rows = weapon_rows(request)
    monster = next(r for r in rows if r["wargear_id"] == f"{WRAITHLORD}:shuriken-catapult")
    infantry = next(r for r in rows if r["wargear_id"] == f"{LORD}:bolt-pistol")
    assert monster["model_instance_id"] == body.own_model_ids()[0]
    assert infantry["model_instance_id"] == leader.own_model_ids()[0]
    before = session.lifecycle.to_payload()
    invalid = submit(
        session, [infantry], ["enemy:outside"], "close_quarters", result_id="mixed:reject"
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert pending(session) == request
    assert_valid(
        submit(
            session,
            [monster, infantry],
            ["enemy:outside", "enemy:target"],
            "close_quarters",
            result_id="mixed:legal",
        )
    )
    pools = accepted_pools(session)
    assert len(pools) == 2
    by_model = {p["attacker_model_instance_id"]: p for p in pools}
    assert by_model[body.own_model_ids()[0]]["hit_roll_modifier"] == -1
    assert by_model[leader.own_model_ids()[0]]["hit_roll_modifier"] == 0
    assert by_model[body.own_model_ids()[0]]["target_unit_instance_id"] == "enemy:outside"
    assert by_model[leader.own_model_ids()[0]]["target_unit_instance_id"] == "enemy:target"
    finish_attacks(session)
    assert state.shooting_phase_state is not None
    assert formation.attached_unit_instance_id in state.shooting_phase_state.shot_unit_ids
    assert pending(session).decision_type == "select_shooting_unit"
