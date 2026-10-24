"""02.02 wounds / 02.02.04 healing / 02.02.05 full wounds: direct engine owners."""

import pytest

from tests.support.section02_fixtures import Section02Definitions, health_state
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.damage_allocation import (
    DamageKind,
    apply_damage_to_model,
    model_by_id,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.healing import (
    HealingEffect,
    HealingStepKind,
    resolve_healing_until_blocked,
)
from warhammer40k_core.engine.phase import GameLifecycleError


@pytest.mark.parametrize(
    ("damage", "remaining", "destroyed", "excess"),
    [
        (1, 1, False, 0),
        (2, 0, True, 0),
        (3, 0, True, 1),
    ],
)
def test_02_02_wound_threshold_and_excess_damage(
    section02_definitions: Section02Definitions,
    damage: int,
    remaining: int,
    destroyed: bool,
    excess: int,
) -> None:
    unit = section02_definitions.unit()
    state = health_state(section02_definitions, unit)
    model = unit.own_models[0]
    result = apply_damage_to_model(
        state=state,
        target_unit_instance_id=unit.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=damage,
        damage_kind=DamageKind.NORMAL,
        remove_destroyed_model=False,
    )
    assert result.final_wounds_remaining == remaining
    assert result.destroyed is destroyed
    assert result.excess_damage_lost == excess
    assert (
        model_by_id(state=state, model_instance_id=model.model_instance_id).is_alive
        is not destroyed
    )
    assert all(m.current_wounds == 2 for m in state.army_definitions[0].units[0].own_models[1:])
    assert unit.own_models[0].current_wounds == 2


@pytest.mark.parametrize("amount", [1, 3])
def test_02_02_04_healing_restores_one_wound_without_exceeding_starting_wounds(
    section02_definitions: Section02Definitions,
    amount: int,
) -> None:
    unit = section02_definitions.unit()
    state = health_state(section02_definitions, unit)
    model = unit.own_models[0]
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=unit.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=1,
        damage_kind=DamageKind.NORMAL,
    )
    effect, request = resolve_healing_until_blocked(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        effect=HealingEffect("section02-heal", unit.unit_instance_id, amount, "opponent"),
    )
    assert request is None
    assert effect.is_complete()
    assert sum(s.step_kind is HealingStepKind.HEAL_WOUND for s in effect.resolved_steps) == 1
    healed = model_by_id(state=state, model_instance_id=model.model_instance_id)
    assert healed.current_wounds == healed.initial_wounds == 2


def test_02_02_04_model_scope_discards_excess_and_does_not_revive(
    section02_definitions: Section02Definitions,
) -> None:
    unit = section02_definitions.unit()
    state = health_state(section02_definitions, unit)
    selected, other, dead = unit.own_models[:3]
    for model, amount in ((selected, 1), (other, 1), (dead, 2)):
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=amount,
            damage_kind=DamageKind.NORMAL,
            remove_destroyed_model=False,
        )
    effect, request = resolve_healing_until_blocked(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        effect=HealingEffect(
            "model-heal",
            unit.unit_instance_id,
            5,
            "opponent",
            source_context={"healing_model_instance_id": selected.model_instance_id},
        ),
    )
    assert request is None
    assert effect.is_complete()
    assert [
        model_by_id(state=state, model_instance_id=m.model_instance_id).current_wounds
        for m in (selected, other, dead)
    ] == [2, 1, 0]
    assert sum(s.step_kind is HealingStepKind.HEAL_WOUND for s in effect.resolved_steps) == 1


def test_02_02_04_foreign_model_scope_fails_before_healing(
    section02_definitions: Section02Definitions,
) -> None:
    unit = section02_definitions.unit()
    state = health_state(section02_definitions, unit)
    before = state.army_definitions[0].to_payload()
    with pytest.raises(GameLifecycleError, match="belong"):
        resolve_healing_until_blocked(
            state=state,
            decisions=DecisionController(),
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            effect=HealingEffect(
                "wrong-model",
                unit.unit_instance_id,
                1,
                "opponent",
                source_context={"healing_model_instance_id": "foreign"},
            ),
        )
    assert state.army_definitions[0].to_payload() == before
