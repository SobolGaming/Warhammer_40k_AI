"""Exact engagement boundaries, model-scoped contracts and non-shooting isolation."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import (
    axis_endpoint_within_range,
    geometry,
    native_state,
    scenario,
)
from tests.support.section04_fixtures import (
    choose,
    combat_state,
    pending,
)
from tests.support.section09_fixtures import add_unit
from tests.support.section10_fixtures import (
    AVENGERS,
    DEFILER,
    LORD,
    SPINNER,
    assert_valid,
    case,
    declaration_request,
    shooting_mission,
    submit,
)
from tests.support.section10_fixtures import shooting_session as combat_session
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.activity_restrictions import has_activity_restriction
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.phases.movement import FellBackUnitState
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_engagement import CLOSE_QUARTERS_SHOOTING_SOURCE_ID
from warhammer40k_core.engine.shooting_targets import shooting_target_candidate_for_model
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("delta", [-0.001, 0, 0.001])
@pytest.mark.parametrize("vertical", [False, True])
@pytest.mark.parametrize("origin", [2, 10])
def test_native_engagement_boundary_changes_normal_and_close_quarters_choices(
    section10_definitions: Section02Definitions, delta: float, vertical: bool, origin: float
) -> None:
    d = section10_definitions
    unit = d.unit(LORD)
    enemy = d.unit(LORD, identity="target", army_id="enemy")
    model = geometry(unit, (Pose.at(origin, 10),))[0]
    assert isinstance(model.base, CircularBase)
    x = axis_endpoint_within_range(
        origin, model.base.radius, model.base.radius, 1.5 if vertical else 2 + delta
    )
    z = model.volume.height + 5 + delta if vertical else 0
    state = native_state(d, unit, (model.pose,), enemy=enemy, enemy_poses=(Pose.at(x, 10, z=z),))
    target_geometry = geometry(enemy, (Pose.at(x, 10, z=z),), enemy=True)[0]
    measured = model.base_distance_to(target_geometry)
    assert abs(measured - (1.5 if vertical else 2 + delta)) <= 1e-12
    if not vertical and delta == 0:
        print(
            f"Section10 inclusive native edge: origin={origin}, "
            f"radius={model.base.radius!r}, x={x!r}, measured={measured!r}"
        )
    from warhammer40k_core.engine.phase import BattlePhase

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    session = combat_session(d, state, shooting_mission())
    choose(session, pending(session), unit.unit_instance_id)
    assert {o.option_id for o in pending(session).options} == (
        {"close_quarters"} if delta <= 0 else {"normal"}
    )


@pytest.mark.parametrize("permitted", [False, True])
def test_fall_back_receipt_restricts_shooting_until_explicit_permission(
    section10_definitions: Section02Definitions, permitted: bool
) -> None:
    d = section10_definitions
    unit = d.unit(LORD)
    state = combat_state(d, unit)
    # Constructed completed-move receipt; tests the consuming shooting boundary.
    state.record_fell_back_unit_state(
        FellBackUnitState("owner", 1, unit.unit_instance_id, can_shoot=permitted)
    )
    session = combat_session(d, state, shooting_mission())
    assert (unit.unit_instance_id in {o.option_id for o in pending(session).options}) is permitted
    if permitted:
        choose(session, pending(session), unit.unit_instance_id)
        assert {o.option_id for o in pending(session).options} == {"normal"}


@pytest.mark.parametrize("close_quarters", [False, True])
@pytest.mark.parametrize("own_target", [False, True])
def test_constructed_vehicle_sidearm_exception_is_specific_to_engaged_target(
    section10_definitions: Section02Definitions, close_quarters: bool, own_target: bool
) -> None:
    d = section10_definitions
    unit = d.unit(DEFILER)
    state = combat_state(d, unit, distance=5)
    from tests.support.section04_fixtures import add_enemy

    add_enemy(d, state, identity="outside", x=10, y=22)
    native = d.weapon(f"{DEFILER}:excruciator-cannon")
    # Explicit Core keyword-combination contract absent from this native loadout.
    profile = (
        replace(native, keywords=(*native.keywords, WeaponKeyword.CLOSE_QUARTERS))
        if close_quarters
        else native
    )
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=unit,
        attacker_model_instance_id=unit.own_model_ids()[0],
        weapon_profile=profile,
        target_unit_id="enemy:target" if own_target else "enemy:outside",
    )
    assert result.is_legal
    expected = 0 if close_quarters and own_target else -1
    assert result.hit_roll_modifier == expected
    assert (CLOSE_QUARTERS_SHOOTING_SOURCE_ID in result.targeting_rule_ids) is (expected == -1)


def test_constructed_mixed_attachment_preserves_each_models_shooting_permissions(
    section10_definitions: Section02Definitions,
) -> None:
    d = section10_definitions
    body = d.unit(DEFILER)
    leader = d.unit(LORD, identity="leader")
    state = combat_state(d, body, distance=5)
    add_unit(state, leader, (Pose.at(10, 15.5),))
    formation = AttachedUnitFormation(
        "attached-unit:section02:mixed",
        body.unit_instance_id,
        (leader.unit_instance_id,),
        component_unit_instance_ids=tuple(sorted((body.unit_instance_id, leader.unit_instance_id))),
        source_id="constructed:section10:mixed",
        attachment_source_ids=("constructed:section10:mixed",),
    )
    state.army_definitions[0] = replace(state.army_definitions[0], attached_units=(formation,))
    from tests.support.section04_fixtures import add_enemy

    add_enemy(d, state, identity="outside", x=16, y=16)
    from warhammer40k_core.engine.shooting_targets import (
        _locked_in_combat_validation,  # pyright: ignore[reportPrivateUsage]
    )

    # Constructed engaged-target boundary at the actual model-policy consumer.
    # The earlier full mixed-body visibility pilot is retained with its Z3
    # timeout stack; full LoS adds no proof of keyword scope here. Ordinary
    # native facade cases separately exercise complete geometry and attacks.
    for physical, suffix, expected in [
        (body, "excruciator-cannon", True),
        (leader, "bolt-pistol", False),
    ]:
        result = _locked_in_combat_validation(
            attacker_model_keywords=physical.own_models[0].keywords,
            weapon_profile=d.weapon(f"{physical.datasheet_id}:{suffix}"),
            target_unit_id="enemy:outside",
            engaged_target_unit_ids=("enemy:target",),
            indirect_no_visible=False,
        )
        assert (result is None) is expected
    assert (
        "VEHICLE"
        in rules_unit_view_by_id(
            state=state, unit_instance_id=formation.attached_unit_instance_id
        ).keywords
    )
    assert "VEHICLE" not in leader.own_models[0].keywords


@pytest.mark.parametrize(
    ("sheet", "kind", "advance", "engaged"),
    [
        (LORD, "normal", False, False),
        (AVENGERS, "assault", True, False),
        (LORD, "close_quarters", False, True),
        (SPINNER, "indirect", False, False),
    ],
)
def test_empty_selection_resolves_after_shooting_action_restriction(
    section10_definitions: Section02Definitions, sheet: str, kind: str, advance: bool, engaged: bool
) -> None:
    session, state, unit = case(section10_definitions, sheet, advance=advance, engaged=engaged)
    declaration_request(session, unit, kind)
    assert_valid(submit(session, [], [], kind))
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
    assert has_activity_restriction(state=state, rules_unit=view, activity="completed_shooting")
    assert state.shooting_phase_state is not None
    assert unit.unit_instance_id not in state.shooting_phase_state.shot_unit_ids
