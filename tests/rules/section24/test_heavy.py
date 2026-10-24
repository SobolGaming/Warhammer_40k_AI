"""Native Movement submissions reach Heavy without mustering or earlier phases."""

from math import isclose
from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state, scenario
from tests.support.section03_session import movement_session
from tests.support.section09_fixtures import add_unit, attach_mission, begin
from tests.support.section24_fixtures import AVENGERS, LORD, profile_grant
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword
from warhammer40k_core.engine.attack_sequence_dispatch import resolve_attack_sequence_until_blocked
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.shooting_declaration_validation import (
    _apply_phase13d_weapon_modifiers,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("action", ["normal_move", "advance"])
@pytest.mark.parametrize("distance", [3.0, 3.001])
@pytest.mark.parametrize("returning_index", [0, -1])
def test_each_native_model_accepted_return_path_controls_actual_heavy_hit(
    section24_definitions: Section02Definitions, action: str, distance: float, returning_index: int
) -> None:
    d = section24_definitions
    own = d.unit(AVENGERS)
    target = d.unit(LORD, army_id="enemy", identity="target")
    poses = tuple(Pose.at(10, 10 + 1.5 * i) for i in range(len(own.own_models)))
    state = native_state(d, own, poses, enemy=target, enemy_poses=(Pose.at(25, 10),))
    attach_mission(state)
    add_unit(state, d.unit(LORD, identity="spare"), (Pose.at(10, 35),))
    session = movement_session(d, state)
    request = begin(session)
    status = session.submit_option(
        request_id=request.request_id, result_id="s24:heavy-unit", option_id=own.unit_instance_id
    )
    assert status.decision_request is not None
    request = status.decision_request
    status = session.submit_option(
        request_id=request.request_id, result_id="s24:heavy-mode", option_id=action
    )
    assert status.decision_request is not None
    request = status.decision_request
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    returning_id = own.own_model_ids()[returning_index]
    paths = tuple(
        (
            mid,
            (p, Pose.at(10 + (distance + 1) / 2, p.position.y), Pose.at(11, p.position.y))
            if mid == returning_id
            else (p, Pose.at(11, p.position.y)),
        )
        for mid, p in zip(own.own_model_ids(), poses, strict=True)
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s24:heavy-path",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=context.proposal_kind,
                unit_instance_id=own.unit_instance_id,
                movement_phase_action=action,
                movement_mode="normal" if action == "normal_move" else "advance",
                witness=PathWitness.for_paths(paths),
            ).to_payload()
        ),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    rows = {r.model_instance_id: r for r in state.model_movement_history}
    assert isclose(rows[returning_id].distance_inches, distance)
    assert all(
        isclose(rows[mid].distance_inches, 1) for mid in own.own_model_ids() if mid != returning_id
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    physical = next(
        w
        for w in equipped_weapon_profile_instances_for_model(
            model=own.own_models[0], army_catalog=d.package.army_catalog
        )
        if w.wargear_id == f"{AVENGERS}:avenger-shuriken-catapult"
    )
    profile = profile_grant(physical.weapon_profile, WeaponKeyword.HEAVY, AbilityDescriptor.heavy())
    assert profile.skill is not None
    assert profile.skill.final == 3
    shooting_type = ShootingType.ASSAULT if action == "advance" else ShootingType.NORMAL
    _, rule_ids, modifier = _apply_phase13d_weapon_modifiers(
        state=state,
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=own.unit_instance_id),
        target_rules_unit=rules_unit_view_by_id(
            state=state, unit_instance_id=target.unit_instance_id
        ),
        weapon_profile=profile,
        shooting_type=shooting_type,
        base_attacks=1,
        base_targeting_rule_ids=(),
        base_hit_roll_modifier=0,
        target_within_half_range=False,
        terrain_features=(),
        player_id="owner",
    )
    assert modifier == int(distance <= 3)
    assert ("weapon-ability:heavy" in rule_ids) is (distance <= 3)
    # One representative native attack, with explicit Core Heavy grant; no
    # changed datasheet or native faction-provider admission is inferred.
    pool = RangedAttackPool(
        physical.weapon_instance_id,
        physical.model_instance_id,
        physical.wargear_id,
        profile.profile_id,
        profile,
        target.unit_instance_id,
        shooting_type,
        1,
        target.own_model_ids(),
        target.own_model_ids(),
        targeting_rule_ids=rule_ids,
        hit_roll_modifier=modifier,
        hit_roll_modifiers=(
            RollModifier("weapon-ability:heavy", modifier, source_id="weapon-ability:heavy"),
        )
        if modifier
        else (),
    )
    decisions = DecisionController()
    rolls = tuple(
        DiceRollResult.from_values(
            roll_id=f"s24:heavy:{kind}",
            spec=DiceRollSpec(
                expression=DiceExpression(1, 6),
                reason=(
                    f"{kind.capitalize()} roll for {profile.profile_id} "
                    "attack heavy:pool-001:attack-001"
                ),
                roll_type=f"attack_sequence.{kind}",
                actor_id="owner",
            ),
            values=(value,),
            source="fixed",
        )
        for kind, value in (("hit", 2), ("wound", 1))
    )
    remaining, _, blocked = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attack_sequence=AttackSequence.start(
            sequence_id="heavy",
            attacker_player_id="owner",
            attacking_unit_instance_id=own.unit_instance_id,
            attack_pools=(pool,),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "heavy", event_log=decisions.event_log, injected_results=rolls
        ),
    )
    assert remaining is None
    assert blocked is None
    (hit,) = [
        e.payload
        for e in decisions.event_log.records
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload["step"] == "hit"
    ]
    result = cast(dict[str, JsonValue], hit["payload"])
    assert result["successful"] is (distance <= 3)
    assert result["capped_modifier"] == int(distance <= 3)
