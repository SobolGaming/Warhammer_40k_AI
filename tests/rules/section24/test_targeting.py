"""Model-complete native/attached abilities reach real target geometry."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state, scenario
from tests.support.section19_fixtures import attached_scene
from tests.support.section24_fixtures import LORD, RANGERS, bolt, with_core
from warhammer40k_core.engine.lone_operative import lone_operative_profile_for_rules_unit
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_targets import shooting_target_candidate_for_model
from warhammer40k_core.engine.stealth import rules_unit_has_native_stealth
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("gap", [10, 14, 17])
@pytest.mark.parametrize("distance", [12, 15])
@pytest.mark.parametrize("indirect", [False, True])
def test_lone_operative_numeric_visibility_also_restricts_indirect(
    section24_definitions: Section02Definitions, gap: int, distance: int, indirect: bool
) -> None:
    from tests.support.section24_fixtures import profile_grant
    from warhammer40k_core.core.weapon_profiles import RangeProfile, WeaponKeyword

    d = section24_definitions
    own = d.unit(LORD)
    target = with_core(
        d.unit(LORD, army_id="enemy", identity="target"), "lone-operative", str(distance)
    )
    state = native_state(
        d, own, (Pose.at(10, 10),), enemy=target, enemy_poses=(Pose.at(10 + gap, 10),)
    )
    p = replace(bolt(d), range_profile=RangeProfile.distance(24))
    if indirect:
        p = profile_grant(p, WeaponKeyword.INDIRECT_FIRE)
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=own,
        attacker_model_instance_id=own.own_model_ids()[0],
        weapon_profile=p,
        target_unit_id=target.unit_instance_id,
    )
    # Physical bases reduce centre separation by less than two inches.
    assert result.is_legal is (gap <= distance)
    assert (result.violation_code is not None) is (gap > distance)


@pytest.mark.parametrize("body_has", [False, True])
@pytest.mark.parametrize("body_alive", [False, True])
def test_attached_lone_operative_requires_every_remaining_component_and_highest_range(
    section24_definitions: Section02Definitions, body_has: bool, body_alive: bool
) -> None:
    from tests.support.section05_fixtures import replace_unit

    s = attached_scene(section24_definitions)
    replace_unit(s.state, with_core(s.leader, "lone-operative", "12"))
    if body_has:
        replace_unit(s.state, with_core(s.body, "lone-operative", "15"))
    if not body_alive:
        s.set_living("bodyguard", 0)
    profile = lone_operative_profile_for_rules_unit(s.view)
    assert (profile is not None) is (body_has or not body_alive)
    if profile is not None:
        assert profile.range_inches == (15 if body_has and body_alive else 12)


@pytest.mark.parametrize("all_models", [False, True])
def test_native_ranger_stealth_requires_every_physical_model_and_marks_target(
    section24_definitions: Section02Definitions, all_models: bool
) -> None:
    from tests.unit_keyword_helpers import with_model_keywords

    d = section24_definitions
    own = d.unit(LORD)
    target = d.unit(RANGERS, army_id="enemy", identity="target")
    assert any(
        a.core_family is not None and a.core_family.value == "stealth"
        for a in target.datasheet_abilities
    )
    if not all_models:
        target = replace(
            target,
            datasheet_abilities=(),
            own_models=tuple(
                with_model_keywords(m, keywords=(*m.keywords, "STEALTH")) if i else m
                for i, m in enumerate(target.own_models)
            ),
        )
    state = native_state(
        d,
        own,
        (Pose.at(10, 10),),
        enemy=target,
        enemy_poses=tuple(Pose.at(18, 10 + 1.5 * i) for i in range(len(target.own_models))),
    )
    view = rules_unit_view_by_id(state=state, unit_instance_id=target.unit_instance_id)
    assert rules_unit_has_native_stealth(view) is all_models
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=own,
        attacker_model_instance_id=own.own_model_ids()[0],
        weapon_profile=bolt(d),
        target_unit_id=target.unit_instance_id,
    )
    assert result.is_legal
    assert ("stealth" in result.targeting_rule_ids) is all_models
