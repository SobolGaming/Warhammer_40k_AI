"""Core unit healing priority and revival through the real reserve consumer."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions, health_state
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
from warhammer40k_core.engine.damage_allocation import (
    DamageKind,
    apply_damage_to_model,
    model_by_id,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.healing import (
    HealingEffect,
    HealingStepKind,
    apply_healing_model_decision,
    resolve_healing_until_blocked,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
)
from warhammer40k_core.engine.unit_state import StartingStrengthRecord


@pytest.mark.parametrize("healing", [1, 2, 3])
def test_02_02_04_wounded_member_precedes_one_wound_revival(
    section02_definitions: Section02Definitions,
    healing: int,
) -> None:
    unit = section02_definitions.unit()
    state = health_state(section02_definitions, unit)
    wounded, dead = unit.own_models[:2]
    for model, damage in ((wounded, 1), (dead, 2)):
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=damage,
            damage_kind=DamageKind.NORMAL,
            remove_destroyed_model=False,
        )
    state.record_battlefield_state(
        BattlefieldRuntimeState(
            "reserve-health", 60, 44, (), removed_model_ids=(dead.model_instance_id,)
        )
    )
    state.record_reserve_state(
        ReserveState(
            "owner",
            unit.unit_instance_id,
            ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            ReserveKind.STRATEGIC_RESERVES,
            "declare_battle_formations",
            None,
            None,
            ReserveDestructionTimingPolicy.core_rules_default(),
        )
    )
    decisions = DecisionController()
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    effect, request = resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=descriptor,
        effect=HealingEffect("priority", unit.unit_instance_id, healing, "opponent"),
    )
    assert model_by_id(state=state, model_instance_id=wounded.model_instance_id).current_wounds == 2
    assert model_by_id(state=state, model_instance_id=dead.model_instance_id).current_wounds == 0
    assert effect.resolved_steps[0].step_kind is HealingStepKind.HEAL_WOUND
    if healing == 1:
        assert request is None
        assert effect.is_complete()
        return
    assert request is not None
    assert len(request.options) == 1
    result = DecisionResult.for_request(
        result_id="choose-dead", request=request, selected_option_id=request.options[0].option_id
    )
    effect, request = apply_healing_model_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=descriptor,
        effect=effect,
        result=result,
    )
    assert request is None
    assert effect.is_complete()
    assert effect.resolved_steps[1].step_kind is HealingStepKind.REVIVE_MODEL_IN_RESERVES
    assert effect.resolved_steps[1].final_wounds_remaining == 1
    assert (
        model_by_id(state=state, model_instance_id=dead.model_instance_id).current_wounds
        == healing - 1
    )
    assert state.battlefield_state is not None
    assert dead.model_instance_id not in state.battlefield_state.removed_model_ids


def test_02_02_04_core_unit_healing_cannot_revive_a_character(
    section02_definitions: Section02Definitions,
) -> None:
    leader = section02_definitions.unit(LORD_EXULTANT)
    state = health_state(section02_definitions, section02_definitions.unit())
    state.army_definitions[:] = [replace(state.army_definitions[0], units=(leader,))]
    state.starting_strength_records[:] = [
        StartingStrengthRecord.from_unit(player_id="owner", unit=leader)
    ]
    model = leader.own_models[0]
    assert "CHARACTER" in model.keywords
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=leader.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=model.initial_wounds,
        damage_kind=DamageKind.NORMAL,
        remove_destroyed_model=False,
    )
    state.record_battlefield_state(
        BattlefieldRuntimeState(
            "character-health", 60, 44, (), removed_model_ids=(model.model_instance_id,)
        )
    )
    effect, request = resolve_healing_until_blocked(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        effect=HealingEffect("no-character-revival", leader.unit_instance_id, 3, "opponent"),
    )
    assert request is None
    assert all(step.step_kind is HealingStepKind.NO_EFFECT for step in effect.resolved_steps)
    assert not model_by_id(state=state, model_instance_id=model.model_instance_id).is_alive
