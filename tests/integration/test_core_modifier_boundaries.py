from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.generic_modifier_helpers import generic_effect
from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _first_weapon_profile,
    _ruleset,
    _shooting_lifecycle,
    _state,
)
from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollState
from warhammer40k_core.core.modified_dice import ModifiedRollResult, ModifiedRollResultPayload
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.weapon_profiles import DamageProfile, RangeProfile
from warhammer40k_core.engine.advance_roll import AdvanceRollRequest, AdvanceRollResult
from warhammer40k_core.engine.attack_sequence_geometry_targets import _damage_value
from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _roll_wound
from warhammer40k_core.engine.attack_sequence_model import (
    HitRoll,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.charge_declaration import ChargeRollResult, ChargeRollResultPayload
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.lone_operative import lone_operative_target_allowed
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.saves import SaveKind, SaveOption, resolve_saving_throw
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetViolationCode,
    shooting_target_candidate_for_model,
)
from warhammer40k_core.engine.stratagems_generic_rule_ir_runtime import (
    GENERIC_RULE_IR_CHARGE_ROLL_MODIFIER_EFFECT_KIND,
)
from warhammer40k_core.engine.unit_abilities import LoneOperativeAbilityProfile
from warhammer40k_core.geometry.pose import Pose


def test_hit_wound_and_save_consumers_keep_natural_one_separate_from_negative_modifiers() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker, target = units["intercessor-1"], units["enemy"]
    pool = _attack_pool_for_test(
        attacker=attacker,
        defender=target,
        weapon_profile=_first_weapon_profile(lifecycle, attacker),
        attacks=1,
    )
    state.record_persisting_effect(
        generic_effect(
            effect_id="hit-penalty",
            owner_player_id="player-b",
            target_unit_instance_ids=(target.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "hit", "delta": -10},
        )
    )
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=pool.weapon_profile_id,
        attack_context_id="limits-hit",
        attacker_player_id="player-a",
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=pool.weapon_profile_id,
        attack_context_id="limits-wound",
        attacker_player_id="player-a",
    )
    hit_manager = DiceRollManager(
        "hit",
        injected_results=(
            DiceRollResult.from_values(
                roll_id="roll-000001", spec=hit_spec, values=(1,), source="rng"
            ),
        ),
    )
    wound_manager = DiceRollManager(
        "wound",
        injected_results=(
            DiceRollResult.from_values(
                roll_id="roll-000001", spec=wound_spec, values=(1,), source="rng"
            ),
        ),
    )
    hit = _roll_hit(
        state=state,
        manager=hit_manager,
        pool=pool,
        attacker_player_id="player-a",
        attack_context_id="limits-hit",
        source_phase=BattlePhase.SHOOTING,
    )
    wound = _roll_wound(
        manager=wound_manager,
        pool=pool,
        toughness=4,
        attacker_player_id="player-a",
        attack_context_id="limits-wound",
        critical_threshold=6,
        wound_modifier=-10,
    )
    for result in (hit, wound):
        assert result.unmodified_roll == 1
        assert result.capped_modifier == -1
        assert result.final_roll == 1
        assert not result.successful
    assert HitRoll.from_payload(hit.to_payload()) == hit
    assert json.loads(json.dumps(wound.to_payload()))["final_roll"] == 1
    assert hit.roll_state is not None
    save = resolve_saving_throw(
        option=SaveOption(
            save_kind=SaveKind.ARMOUR,
            target_number=6,
            characteristic_target_number=3,
            armor_penetration=-3,
        ),
        roll_state=hit.roll_state,
    )
    assert save.unmodified_roll == save.final_roll == 1
    assert not save.successful


def test_modifier_source_artifact_matches_reviewed_evidence_and_rejects_drift() -> None:
    from tools.build_core_modifiers_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_modifiers_2026_09 as source,
    )

    payload, audit = build_payloads()
    assert json.loads(ARTIFACT_PATH.read_bytes()) == payload
    assert json.loads(AUDIT_PATH.read_bytes()) == audit
    package = source.source_package()
    assert len(source.source_rules()) == 3
    for rule in source.source_rules():
        assert rule.source_id in package.evidence_required_source_ids
        assert package.source_catalog.source_text_by_id(rule.source_id).raw_text == rule.source_text
        assert rule.load_support_status == "loaded"
        assert rule.semantic_execution_status == "executable_engine_runtime"
        assert rule.runtime_consumer_ids
    with pytest.raises(source.CoreModifiersSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


@pytest.mark.parametrize("delta", [-100, 2])
def test_random_damage_preserves_intrinsic_expression_and_modified_event(delta: int) -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker, target = units["intercessor-1"], units["enemy"]
    profile = _first_weapon_profile(lifecycle, attacker)
    state.record_persisting_effect(
        generic_effect(
            effect_id="damage-modifier",
            owner_player_id="player-a",
            target_unit_instance_ids=(target.unit_instance_id,),
            target_kind="selected_target",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "damage", "delta": delta, "attack_role": "target"},
        )
    )
    value, status = _damage_value(
        state=state,
        decisions=lifecycle.decision_controller,
        manager=DiceRollManager("order27-damage"),
        profile=DamageProfile.dice(DiceExpression(quantity=1, sides=6, modifier=1)),
        attack_context_id="attack:damage",
        attacker_player_id="player-a",
        affected_unit_instance_id=attacker.unit_instance_id,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=target.unit_instance_id,
        weapon_profile=profile,
        source_phase=BattlePhase.SHOOTING,
        stratagem_index=None,
    )
    assert status is None
    event = lifecycle.decision_controller.event_log.records[-1]
    assert event.event_type == "random_characteristic_rolled"
    assert isinstance(event.payload, dict)
    trace = ModifiedRollResult.from_payload(
        cast(ModifiedRollResultPayload, event.payload["modified_roll"])
    )
    assert trace.intrinsic_offset == 1
    assert event.payload["value"] == trace.unmodified.value + 1
    assert trace.unbounded_value == trace.unmodified.value + 1 + delta
    assert value == trace.final_value == max(1, trace.unbounded_value)


@pytest.mark.parametrize(("delta", "expected"), [(100, 12), (-100, 1)])
def test_charge_limits_reach_facade_events_restore_and_exact_replay(
    delta: int, expected: int
) -> None:
    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("charger",),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(20, 20), model_count=5),
        game_id=f"order27-charge-{delta}",
    )
    state = lifecycle.state
    assert state is not None
    unit_id = units["charger"].unit_instance_id
    # A real, serialized generic effect exercises the production collection path.
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="fixture:charge-modifier",
            source_rule_id="fixture:charge-source",
            owner_player_id="player-a",
            target_unit_instance_ids=(unit_id,),
            started_battle_round=1,
            started_phase=None,
            expiration=EffectExpiration.end_of_battle(),
            effect_payload={
                "effect_kind": GENERIC_RULE_IR_CHARGE_ROLL_MODIFIER_EFFECT_KIND,
                "source_rule_id": "fixture:charge-source",
                "stratagem_id": "fixture:charge-stratagem",
                "stratagem_use_id": "fixture:charge-use",
                "target_unit_instance_id": unit_id,
                "roll_type": "charge",
                "delta": delta,
                "generic_rule_execution_result": {"status": "applied"},
                "generic_rule_effect": {"roll_type": "charge", "delta": delta},
            },
        )
    )
    session = LocalGameSession(lifecycle=lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    session.submit_option(
        request_id=request.request_id, option_id=unit_id, result_id="select-charger"
    )
    event = next(
        e
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "charge_roll_resolved"
    )
    assert isinstance(event.payload, dict)
    payload = cast(ChargeRollResultPayload, event.payload["roll_result"])
    roll = ChargeRollResult.from_payload(payload)
    trace = roll.request.resolve_roll(roll.roll_state)
    assert roll.request.spec.expression.modifier == 0
    assert trace.unmodified.value == sum(roll.roll_state.current_values)
    assert trace.unbounded_value == trace.unmodified.value + delta
    assert trace.modified_value == max(1, trace.unbounded_value)
    assert trace.final_value == roll.value == expected
    assert trace.applied_modifier_ids == ("fixture:charge-modifier",)
    assert event.payload["maximum_distance_inches"] == expected
    for viewer in ("player-a", "player-b"):
        projected = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        public = next(e for e in projected["events"] if e["event_type"] == "charge_roll_resolved")
        assert public["payload"] == event.to_payload()["payload"]
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="order27-charge-replay")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED
    drifted = cast(ChargeRollResultPayload, json.loads(json.dumps(payload)))
    drifted["modified_roll"]["final_value"] += 1
    with pytest.raises(ValueError, match="modif"):
        ChargeRollResult.from_payload(drifted)
    drifted = cast(ChargeRollResultPayload, json.loads(json.dumps(payload)))
    drifted["value"] += 1
    with pytest.raises(GameLifecycleError, match="bounded modified"):
        ChargeRollResult.from_payload(drifted)
    if expected == 1:
        with pytest.raises(GameLifecycleError, match="bounded modified"):
            replace(roll, value=True)


@pytest.mark.parametrize(("delta", "expected"), [(10, 16), (-10, 1)])
def test_advance_retains_raw_dice_and_has_no_six_result_cap(delta: int, expected: int) -> None:
    request = AdvanceRollRequest.for_unit(
        request_id="advance-request",
        game_id="order27-advance",
        battle_round=1,
        player_id="player-a",
        unit_instance_id="army:unit",
        roll_modifiers=(RollModifier("advance-effect", delta),),
    )
    state = DiceRollState.from_result(
        DiceRollResult.from_values(
            roll_id="advance-die",
            spec=request.spec,
            values=(6,),
            source="fixed",
        )
    )
    result = AdvanceRollResult.from_roll_state(request=request, roll_state=state)
    assert state.current_total == 6
    assert result.modified_roll.unbounded_value == 6 + delta
    assert result.value == expected
    assert AdvanceRollResult.from_payload(result.to_payload()) == result
    if expected == 1:
        with pytest.raises(GameLifecycleError, match="bounded modifier"):
            replace(result, value=True)


@pytest.mark.parametrize(
    ("base_range", "bonus", "target_x", "expected"),
    [
        (1.0, 0, 19.4, True),
        (1.0, 0, 21.0, False),
        (100.0, 0, 39.0, True),
        (100.0, 0, 43.0, False),
        (1.0, 20, 29.0, True),
        (1.0, 20, 35.0, False),
    ],
)
def test_hidden_detection_uses_the_shared_terminal_range(
    base_range: float,
    bonus: int,
    target_x: float,
    expected: bool,
) -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(target_x, 35),
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
    )
    attacker, target = units["intercessor-1"], units["enemy"]
    ruleset = _ruleset()
    ruleset = replace(
        ruleset,
        descriptor_hash="",
        terrain_visibility_policy=replace(
            ruleset.terrain_visibility_policy,
            hidden_detection_range_inches=base_range,
        ),
    )
    profile = replace(
        _first_weapon_profile(lifecycle, attacker), range_profile=RangeProfile.distance(100)
    )
    candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_profile=profile,
        target_unit_id=target.unit_instance_id,
        hidden_target_model_ids=tuple(m.model_instance_id for m in target.own_models),
        target_detection_range_bonus_inches=bonus,
    )
    assert candidate.is_legal is expected
    if not expected:
        assert candidate.violation_code is ShootingTargetViolationCode.OUTSIDE_DETECTION_RANGE


@pytest.mark.parametrize(
    ("range_inches", "target_x", "expected"),
    [
        (1.0, 19.4, True),
        (1.0, 21.0, False),
        (100.0, 39.0, True),
        (100.0, 43.0, False),
    ],
)
def test_lone_operative_uses_the_same_terminal_range(
    range_inches: float,
    target_x: float,
    expected: bool,
) -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",), enemy_pose=Pose.at(target_x, 35)
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
    )
    attacker, target = units["intercessor-1"], units["enemy"]
    view = rules_unit_view_from_armies(
        armies=scenario.armies, unit_instance_id=target.unit_instance_id
    )
    assert (
        lone_operative_target_allowed(
            scenario=scenario,
            attacker_unit=attacker,
            attacker_model_instance_id=attacker.own_models[0].model_instance_id,
            target_rules_unit=view,
            profile=LoneOperativeAbilityProfile(
                source_id="fixture:lone-operative", range_inches=range_inches
            ),
        )
        is expected
    )
