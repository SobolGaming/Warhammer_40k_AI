from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import RANGERS, Section02Definitions
from tests.support.section03_fixtures import placement, scenario
from tests.support.section04_melee import melee_case
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_weapon_selection import (
    MeleeTargetAllocation,
    available_melee_weapons_payloads,
    melee_attack_sequence_from_proposal,
    validate_melee_declaration_rules,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("split", [False, True])
def test_native_melee_selects_weapon_and_conserves_declared_split(
    section04_definitions: Section02Definitions, split: bool
) -> None:
    d = section04_definitions
    state, request, proposal = melee_case(d)
    original = proposal.declarations[0]
    row = cast(dict[str, JsonValue], request.available_weapons[0])
    count = cast(int, row["fixed_attacks"])
    if split:
        proposal = replace(
            proposal,
            declarations=(
                replace(
                    original,
                    target_allocations=(
                        MeleeTargetAllocation("enemy:target", count - 1),
                        MeleeTargetAllocation("enemy:other", 1),
                    ),
                ),
            ),
        )
    validation = validate_melee_declaration_rules(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        request=request,
        proposal=proposal,
        army_catalog=d.package.army_catalog,
        state=state,
    )
    assert validation.is_valid, validation
    sequence = melee_attack_sequence_from_proposal(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        proposal=proposal,
        army_catalog=d.package.army_catalog,
        dice_manager=DiceRollManager("section04"),
        sequence_id="melee",
        state=state,
        selected_weapon_rows=request.available_weapons,
    )
    assert [p.attacks for p in sequence.attack_pools] == ([count - 1, 1] if split else [count])
    assert [p.target_unit_instance_id for p in sequence.attack_pools] == (
        ["enemy:target", "enemy:other"] if split else ["enemy:target"]
    )
    assert sum(p.attacks for p in sequence.attack_pools) == count
    assert {p.weapon_instance_id for p in sequence.attack_pools} == {original.weapon_instance_id}
    assert all(
        p.weapon_profile.range_profile.distance_inches is None for p in sequence.attack_pools
    )


@pytest.mark.parametrize(
    ("invalid", "code"),
    [
        ("none", "melee_declaration_required"),
        ("duplicate", "duplicate_melee_weapon_declaration"),
        ("two", "melee_model_declared_multiple_weapons"),
        ("missing", "melee_weapon_not_available"),
        ("target", "melee_target_not_engaged_with_model"),
        ("overspend", "split_melee_attack_count_drift"),
    ],
)
def test_native_melee_rejects_invalid_weapon_and_target_declarations(
    section04_definitions: Section02Definitions, invalid: str, code: str
) -> None:
    d = section04_definitions
    state, request, proposal = melee_case(d)
    first = proposal.declarations[0]
    if invalid == "none":
        proposal = replace(proposal, declarations=())
    elif invalid == "duplicate":
        proposal = replace(proposal, declarations=(first, first))
    elif invalid == "two":
        second = cast(dict[str, JsonValue], request.available_weapons[1])
        proposal = replace(
            proposal,
            declarations=(
                first,
                replace(
                    first,
                    wargear_id=cast(str, second["wargear_id"]),
                    weapon_profile_id=cast(str, second["weapon_profile_id"]),
                    weapon_instance_id=cast(str, second["weapon_instance_id"]),
                ),
            ),
        )
    elif invalid == "missing":
        proposal = replace(
            proposal, declarations=(replace(first, weapon_instance_id="unadvertised:copy"),)
        )
    elif invalid == "target":
        proposal = replace(
            proposal,
            declarations=(
                replace(
                    first, target_allocations=(MeleeTargetAllocation(proposal.unit_instance_id),)
                ),
            ),
        )
    else:
        proposal = replace(
            proposal,
            declarations=(
                replace(
                    first,
                    target_allocations=(
                        MeleeTargetAllocation("enemy:target", 99),
                        MeleeTargetAllocation("enemy:other", 1),
                    ),
                ),
            ),
        )
    before = state.to_payload()
    result = validate_melee_declaration_rules(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        request=request,
        proposal=proposal,
        army_catalog=d.package.army_catalog,
        state=state,
    )
    assert not result.is_valid
    assert result.violations[0].violation_code == code
    assert state.to_payload() == before


def test_native_one_attack_weapon_cannot_select_two_targets(
    section04_definitions: Section02Definitions,
) -> None:
    d = section04_definitions
    state, request, proposal = melee_case(d, datasheet=RANGERS)
    proposal = replace(
        proposal,
        declarations=(
            replace(
                proposal.declarations[0],
                target_allocations=(
                    MeleeTargetAllocation("enemy:target", 1),
                    MeleeTargetAllocation("enemy:other", 1),
                ),
            ),
        ),
    )
    result = validate_melee_declaration_rules(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        request=request,
        proposal=proposal,
        army_catalog=d.package.army_catalog,
        state=state,
    )
    assert not result.is_valid
    assert result.violations[0].violation_code == "melee_target_count_exceeds_attacks"


@pytest.mark.parametrize("count", [0, -1])
def test_each_split_target_requires_positive_attacks(count: int) -> None:
    with pytest.raises(GameLifecycleError, match="greater than zero"):
        MeleeTargetAllocation("enemy:target", count)


def test_native_melee_target_must_remain_engaged_with_bearer(
    section04_definitions: Section02Definitions,
) -> None:
    d = section04_definitions
    state, request, proposal = melee_case(d)
    enemy = next(
        u for a in state.army_definitions for u in a.units if u.unit_instance_id == "enemy:target"
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            placement(enemy, (Pose.at(30, 10),), enemy=True)
        )
    )
    unit = next(
        u
        for a in state.army_definitions
        for u in a.units
        if u.unit_instance_id == proposal.unit_instance_id
    )
    request = replace(
        request,
        available_weapons=available_melee_weapons_payloads(
            scenario=scenario(state),
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            unit=unit,
            army_catalog=d.package.army_catalog,
            state=state,
            source_decision_result_id=request.source_decision_result_id,
        ),
    )
    result = validate_melee_declaration_rules(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        request=request,
        proposal=proposal,
        army_catalog=d.package.army_catalog,
        state=state,
    )
    assert not result.is_valid
    assert result.violations[0].violation_code == "melee_target_not_engaged_with_model"
