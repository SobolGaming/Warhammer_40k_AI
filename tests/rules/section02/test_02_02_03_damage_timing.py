"""Minimal attack sequence: real Maulerfiend fists versus real Infractors."""

from tests.support.section02_consumers import (
    attack_pool,
    combat_state,
    payload_int,
    payload_object,
    payload_text,
    set_origin,
)
from tests.support.section02_fixtures import MAULERFIEND, Section02Definitions
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.attack_sequence_dispatch import resolve_attack_sequence_until_blocked
from warhammer40k_core.engine.attack_sequence_group_selection import (
    apply_allocation_order_decision,
    apply_damage_allocation_model_decision,
)
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import BattlePhase


def test_02_02_03_random_damage_waits_for_each_model_allocation(
    section02_definitions: Section02Definitions,
) -> None:
    attacker = section02_definitions.unit(MAULERFIEND, identity="attacker")
    target = section02_definitions.unit(identity="target", army_id="opponent-army")
    weapon = section02_definitions.weapon(f"{MAULERFIEND}:maulerfiend-fists")
    state = combat_state(section02_definitions, attacker, target)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    set_origin(state, attacker, 10, 10)
    set_origin(state, target, 13.5, 10)
    decisions = DecisionController()
    manager = DiceRollManager("section02-damage", event_log=decisions.event_log)
    current: AttackSequence | None = AttackSequence(
        sequence_id="fists",
        attacker_player_id="owner",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(attack_pool(attacker, target, weapon, f"{MAULERFIEND}:maulerfiend-fists"),),
        source_phase=BattlePhase.FIGHT,
    )
    allocated: tuple[str, ...] = ()
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    status = None
    for iteration in range(15):
        assert current is not None
        if status is None:
            current, allocated, status = resolve_attack_sequence_until_blocked(
                state=state,
                decisions=decisions,
                ruleset_descriptor=descriptor,
                attack_sequence=current,
                already_allocated_model_ids=allocated,
                dice_manager=manager,
            )
        if status is None:
            break
        request = decisions.queue.peek_next()

        assert request.decision_type in {
            "select_allocation_order",
            "select_damage_allocation_model",
        }
        assert current is not None
        if request.decision_type == "select_damage_allocation_model":
            assert isinstance(request.payload, dict)
            context = request.payload["attack_context"]
            assert isinstance(context, dict)
            scope = f"{context['attack_context_id']}:damage"
            assert not any(
                e["event_type"] == "random_characteristic_rolled"
                and payload_object(e["payload"])["scope_id"] == scope
                for e in decisions.event_log.to_payload()
            )
        result = DecisionResult.for_request(
            result_id=f"allocation-{iteration}",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
        decisions.submit_result(result)
        if request.decision_type == "select_damage_allocation_model":
            current, allocated, status = apply_damage_allocation_model_decision(
                state=state,
                decisions=decisions,
                ruleset_descriptor=descriptor,
                attack_sequence=current,
                result=result,
                already_allocated_model_ids=allocated,
                dice_manager=manager,
            )
        else:
            current, allocated, status = apply_allocation_order_decision(
                state=state,
                decisions=decisions,
                ruleset_descriptor=descriptor,
                attack_sequence=current,
                result=result,
                already_allocated_model_ids=allocated,
            )
        if current is None:
            break
    else:
        raise AssertionError("bounded six-attack sequence did not finish")
    events = decisions.event_log.to_payload()
    rolls = [
        payload_object(e["payload"])
        for e in events
        if e["event_type"] == "random_characteristic_rolled"
    ]
    damages = [
        payload_object(e["payload"])
        for e in events
        if e["event_type"] == "attack_sequence_step"
        and payload_object(e["payload"])["step"] == "damage"
    ]
    assert len(rolls) == len(damages) >= 2
    assert len({payload_text(r["scope_id"]) for r in rolls}) == len(rolls)
    assert all(r["characteristic"] == "damage" and r["timing"] == "per_attack" for r in rolls)
    total_wounds = 0
    for damage in damages:
        scope = payload_text(damage["attack_context_id"]) + ":damage"
        roll = next(r for r in rolls if r["scope_id"] == scope)
        application = payload_object(payload_object(damage["payload"])["damage_application"])
        value = payload_int(roll["value"])
        modified = payload_object(roll["modified_roll"])
        assert application["requested_damage"] == value
        assert modified["intrinsic_offset"] == 1
        assert value == payload_int(payload_object(modified["unmodified"])["value"]) + 1
        assert application["wounds_lost"] == min(
            payload_int(application["starting_wounds_remaining"]), value
        )
        total_wounds += payload_int(application["wounds_lost"])
    assert total_wounds == 10
    assert any(e["event_type"] == "attack_sequence_completed" for e in events)
