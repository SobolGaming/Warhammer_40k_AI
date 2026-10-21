"""10.07: native source weapon, visibility, stationary spotting and hit consequences."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_consumers import attack_pool
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import combat_state, weapon_rows
from tests.support.section10_fixtures import (
    LORD,
    SPINNER,
    accepted_pools,
    assert_valid,
    declaration_request,
    shooting_mission,
    submit,
)
from tests.support.section10_fixtures import shooting_session as combat_session
from tests.support.section10_geometry import blocking_wall
from warhammer40k_core.core.dice import DiceRollResult, DiceRollResultPayload, DiceRollState
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.attack_sequence import attack_sequence_hit_roll_spec
from warhammer40k_core.engine.attack_sequence_hit_wound import (
    _benefit_of_cover_ballistic_skill_penalty,
    _roll_hit,
)
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.normal_move_history import NormalMoveSourceKind, NormalMoveState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.weapon_abilities import (
    INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
    INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,
    INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool, RangedAttackPoolPayload


@pytest.mark.parametrize("stationary", [False, True])
@pytest.mark.parametrize("visible", [False, True])
def test_native_indirect_selection_records_cover_no_rerolls_and_spotting(
    section10_definitions: Section02Definitions, stationary: bool, visible: bool
) -> None:
    d = section10_definitions
    unit = d.unit(SPINNER)
    state = combat_state(d, unit, distance=20)
    if not stationary:
        state.record_normal_move_state(
            NormalMoveState(
                "owner",
                "owner",
                1,
                BattlePhase.MOVEMENT,
                unit.unit_instance_id,
                "constructed:prior-move",
                NormalMoveSourceKind.MOVEMENT_PHASE_ACTION,
                "move-request",
                "move-result",
            )
        )
    mission = shooting_mission()
    if not visible:
        mission = replace(mission, terrain_features=(blocking_wall(),))
        assert state.battlefield_state is not None
        state.replace_battlefield_state(
            replace(state.battlefield_state, terrain_features=mission.terrain_features)
        )
    session = combat_session(d, state, mission)
    request = declaration_request(session, unit, "indirect")
    row = next(r for r in weapon_rows(request) if r["wargear_id"] == f"{SPINNER}:doomweaver")
    assert_valid(submit(session, [row], ["enemy:target"], "indirect"))
    payload = accepted_pools(session)[0]
    pool = RangedAttackPool.from_payload(cast(RangedAttackPoolPayload, payload))
    assert bool(pool.target_visible_model_ids) is visible
    assert INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID in pool.targeting_rule_ids
    assert INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID in pool.targeting_rule_ids
    assert (INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID in pool.targeting_rule_ids) is (
        stationary and visible
    )
    assert _benefit_of_cover_ballistic_skill_penalty(state=state, pool=pool) == 1


@pytest.mark.parametrize("spotted", [False, True])
@pytest.mark.parametrize("raw", range(1, 7))
@pytest.mark.parametrize("modifier", [-1, 0, 1])
def test_indirect_unmodified_failure_threshold_and_no_hit_reroll_are_enforced(
    section10_definitions: Section02Definitions, spotted: bool, raw: int, modifier: int
) -> None:
    d = section10_definitions
    attacker = d.unit(SPINNER)
    target = d.unit(LORD, army_id="enemy", identity="target")
    state = combat_state(d, attacker, target=target)
    profile = d.weapon(f"{SPINNER}:doomweaver")
    rules = (
        INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,
        INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
        *((INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID,) if spotted else ()),
    )
    # Typed constructed targeting-boundary contract; integration above proves
    # when native production declarations assign these exact source markers.
    pool = replace(
        attack_pool(attacker, target, profile, f"{SPINNER}:doomweaver"),
        targeting_rule_ids=rules,
        hit_roll_modifier=modifier,
        hit_roll_modifiers=(
            RollModifier("constructed:hit-modifier", modifier, source_id="constructed:section10"),
        )
        if modifier
        else (),
    )
    spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=profile.profile_id,
        attack_context_id="section10:hit",
        attacker_player_id="owner",
        reroll_forbidden_rule_ids=(INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,),
    )
    roll = DiceRollManager("physical").roll_fixed(spec, (raw,)).original_result
    manager = DiceRollManager("section10", injected_results=(roll,))
    hit = _roll_hit(
        state=state,
        manager=manager,
        pool=pool,
        attacker_player_id="owner",
        attack_context_id="section10:hit",
        source_phase=BattlePhase.SHOOTING,
    )
    assert hit.unmodified_roll == raw
    assert hit.successful is (raw >= (4 if spotted else 6) and (raw == 6 or raw + modifier >= 4))
    assert hit.final_roll == max(1, raw + modifier)
    rolled = manager.event_log.records[0].payload
    assert isinstance(rolled, dict)
    actual = DiceRollResult.from_payload(cast(DiceRollResultPayload, rolled))
    assert actual.spec.reroll_forbidden_rule_ids == (INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,)
    before = manager.event_log.records
    with pytest.raises(DecisionError, match="forbid rerolls"):
        manager.request_reroll(DiceRollState.from_result(actual), allowed_selections=((0,),))
    assert manager.event_log.records == before


@pytest.mark.parametrize("stationary", [False, True])
@pytest.mark.parametrize("observer", [False, True])
def test_hidden_target_can_be_spotted_by_a_different_friendly_unit(
    section10_definitions: Section02Definitions, stationary: bool, observer: bool
) -> None:
    d = section10_definitions
    unit = d.unit(SPINNER)
    state = combat_state(d, unit, distance=20)
    mission = replace(shooting_mission(), terrain_features=(blocking_wall(),))
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(state.battlefield_state, terrain_features=mission.terrain_features)
    )
    if not stationary:
        state.record_normal_move_state(
            NormalMoveState(
                "owner",
                "owner",
                1,
                BattlePhase.MOVEMENT,
                unit.unit_instance_id,
                "constructed:prior-move",
                NormalMoveSourceKind.MOVEMENT_PHASE_ACTION,
                "move-request",
                "move-result",
            )
        )
    if observer:
        from tests.support.section09_fixtures import add_unit
        from warhammer40k_core.geometry.pose import Pose

        add_unit(state, d.unit(LORD, identity="observer"), (Pose.at(34, 10),))
    session = combat_session(d, state, mission)
    request = declaration_request(session, unit, "indirect")
    row = next(r for r in weapon_rows(request) if r["wargear_id"] == f"{SPINNER}:doomweaver")
    assert_valid(submit(session, [row], ["enemy:target"], "indirect"))
    pool = accepted_pools(session)[0]
    assert pool["target_visible_model_ids"] == []
    assert isinstance(pool["targeting_rule_ids"], list)
    assert (INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID in pool["targeting_rule_ids"]) is (
        stationary and observer
    )


@pytest.mark.parametrize("visible", [False, True])
def test_normal_type_does_not_gain_indirect_visibility_or_attack_restrictions(
    section10_definitions: Section02Definitions, visible: bool
) -> None:
    d = section10_definitions
    unit = d.unit(SPINNER)
    state = combat_state(d, unit, distance=20)
    mission = shooting_mission()
    if not visible:
        mission = replace(mission, terrain_features=(blocking_wall(),))
        assert state.battlefield_state is not None
        state.replace_battlefield_state(
            replace(state.battlefield_state, terrain_features=mission.terrain_features)
        )
    session = combat_session(d, state, mission)
    request = declaration_request(session, unit, "normal")
    if not visible:
        assert request.decision_type == "select_shooting_unit"
        assert not any(
            e.event_type == "attack_sequence_step"
            for e in session.lifecycle.decision_controller.event_log.records
        )
    else:
        row = next(r for r in weapon_rows(request) if r["wargear_id"] == f"{SPINNER}:doomweaver")
        assert_valid(submit(session, [row], ["enemy:target"], "normal"))
        rules = accepted_pools(session)[0]["targeting_rule_ids"]
        assert isinstance(rules, list)
        assert INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID not in rules
        assert INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID not in rules
        assert INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID not in rules


def test_indirect_callout_other_weapons_can_shoot_different_visible_targets(
    section10_definitions: Section02Definitions,
) -> None:
    from tests.support.section04_fixtures import add_enemy, pending
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    d = section10_definitions
    unit = d.unit(SPINNER)
    state = combat_state(d, unit, distance=20)
    mission = replace(shooting_mission(), terrain_features=(blocking_wall(),))
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(state.battlefield_state, terrain_features=mission.terrain_features)
    )
    add_enemy(d, state, identity="visible", x=10, y=20)
    session = combat_session(d, state, mission)
    request = declaration_request(session, unit, "indirect")
    rows = weapon_rows(request)
    indirect = next(r for r in rows if r["wargear_id"] == f"{SPINNER}:doomweaver")
    ordinary = next(r for r in rows if r["wargear_id"] == f"{SPINNER}:twin-shuriken-catapult")
    before = session.lifecycle.to_payload()
    result = submit(session, [ordinary], ["enemy:target"], "indirect")
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert pending(session) == request
    assert_valid(
        submit(
            session,
            [indirect, ordinary],
            ["enemy:target", "enemy:visible"],
            "indirect",
            result_id="legal-split",
        )
    )
    pools = accepted_pools(session)
    assert len(pools) == 2
    for pool in pools:
        is_indirect = pool["wargear_id"] == f"{SPINNER}:doomweaver"
        assert pool["target_unit_instance_id"] == (
            "enemy:target" if is_indirect else "enemy:visible"
        )
        rules = pool["targeting_rule_ids"]
        assert isinstance(rules, list)
        assert (INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID in rules) is is_indirect
        assert (INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID in rules) is is_indirect
