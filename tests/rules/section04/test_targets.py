"""Native geometry evaluated at the real target-selection boundary."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import (
    AVENGERS,
    INFRACTORS,
    LORD_EXULTANT,
    Section02Definitions,
)
from tests.support.section03_fixtures import scenario
from tests.support.section04_fixtures import combat_state
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetViolationCode,
    shooting_target_candidate_for_model,
)


@pytest.mark.parametrize(("distance", "legal"), [(8, True), (40, False)])
def test_weapon_range_is_measured_from_native_bearer(
    section04_definitions: Section02Definitions, distance: float, legal: bool
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    state = combat_state(d, unit, distance=distance)
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=unit,
        attacker_model_instance_id=unit.own_model_ids()[0],
        weapon_profile=d.weapon(f"{LORD_EXULTANT}:bolt-pistol"),
        target_unit_id="enemy:target",
    )
    assert result.is_legal is legal
    assert result.violation_code is (None if legal else ShootingTargetViolationCode.OUT_OF_RANGE)
    if legal:
        assert result.target_visible_model_ids == result.target_in_range_model_ids
        assert result.line_of_sight_witness is not None


@pytest.mark.parametrize("kind", ["friendly", "melee"])
def test_only_enemy_ranged_targets_are_accepted(
    section04_definitions: Section02Definitions, kind: str
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    state = combat_state(d, unit)
    profile = d.weapon(
        f"{LORD_EXULTANT}:close-combat-weapon"
        if kind == "melee"
        else f"{LORD_EXULTANT}:bolt-pistol"
    )
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=unit,
        attacker_model_instance_id=unit.own_model_ids()[0],
        weapon_profile=profile,
        target_unit_id=unit.unit_instance_id if kind == "friendly" else "enemy:target",
    )
    assert not result.is_legal
    assert result.violation_code is (
        ShootingTargetViolationCode.MELEE_WEAPON
        if kind == "melee"
        else ShootingTargetViolationCode.NOT_ENEMY_UNIT
    )


@pytest.mark.parametrize(
    ("keywords", "legal"),
    [(("INFANTRY",), True), (("VEHICLE",), False), (("VEHICLE", "INFANTRY"), True)],
)
def test_constructed_hunter_gate_requires_any_named_keyword(
    section04_definitions: Section02Definitions, keywords: tuple[str, ...], legal: bool
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    target = d.unit(INFRACTORS, army_id="enemy", identity="target")
    state = combat_state(d, unit, target=target)
    native = d.weapon(f"{LORD_EXULTANT}:bolt-pistol")
    contract = replace(
        native,
        profile_id="constructed:hunter",
        name="Core Hunter contract",
        keywords=(WeaponKeyword.HUNTER,),
        abilities=(AbilityDescriptor.hunter(target_keywords=keywords),),
        source_ids=("constructed:section04:hunter",),
        ability_sources=(),
    )
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=unit,
        attacker_model_instance_id=unit.own_model_ids()[0],
        weapon_profile=contract,
        target_unit_id=target.unit_instance_id,
    )
    assert result.is_legal is legal
    assert result.violation_code is (
        None if legal else ShootingTargetViolationCode.HUNTER_TARGET_KEYWORD_MISMATCH
    )


@pytest.mark.parametrize(("distance", "legal"), [(2.5, False), (8, True)])
def test_native_ordinary_ranged_target_must_be_unengaged(
    section04_definitions: Section02Definitions, distance: float, legal: bool
) -> None:
    d = section04_definitions
    unit = d.unit(AVENGERS)
    state = combat_state(d, unit, distance=distance)
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=unit,
        attacker_model_instance_id=unit.own_model_ids()[0],
        weapon_profile=d.weapon(f"{AVENGERS}:avenger-shuriken-catapult"),
        target_unit_id="enemy:target",
    )
    assert result.is_legal is legal
    assert result.violation_code is (
        None if legal else ShootingTargetViolationCode.LOCKED_IN_COMBAT
    )
