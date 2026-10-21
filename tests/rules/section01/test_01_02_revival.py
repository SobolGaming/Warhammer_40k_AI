"""Explicit Core return contracts consume destroyed native model inventories."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state, reserve_unit
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.healing import (
    HealingEffect,
    HealingStepKind,
    apply_healing_model_decision,
    resolve_healing_until_blocked,
)


@pytest.mark.parametrize("count", [1, 2, 4])
@pytest.mark.parametrize("full", [False, True])
def test_01_02_03_return_count_original_equipment_and_wounds(
    section01_definitions: Section02Definitions, count: int, full: bool
) -> None:
    original = section01_definitions.unit()
    state = minimal_state(section01_definitions, original)
    dead = original.own_models[:2]
    unit = replace(
        original,
        own_models=tuple(
            replace(m, wounds_remaining=0) if m in dead else m for m in original.own_models
        ),
    )
    state.army_definitions[:] = [replace(state.army_definitions[0], units=(unit,))]
    state.record_battlefield_state(
        BattlefieldRuntimeState(
            "revival",
            60,
            44,
            (),
            removed_model_ids=tuple(m.model_instance_id for m in dead),
        )
    )
    reserve_unit(state, unit)
    decisions = DecisionController()
    rules = RulesetDescriptor.warhammer_40000_eleventh()
    effect = HealingEffect(
        "return",
        unit.unit_instance_id,
        count,
        "opponent",
        source_rule_id="constructed:explicit-return",
        source_context={
            "revive_destroyed_models_only": True,
            "revive_model_full_health": full,
        },
    )
    effect, request = resolve_healing_until_blocked(
        state=state, decisions=decisions, ruleset_descriptor=rules, effect=effect
    )
    chosen: list[str] = []
    while request is not None:
        assert request.decision_type == "select_healing_model"
        assert isinstance(request.payload, dict)
        legal_ids = request.payload["legal_model_ids"]
        assert isinstance(legal_ids, list)
        assert all(isinstance(model_id, str) for model_id in legal_ids)
        assert set(legal_ids) == {m.model_instance_id for m in dead} - set(chosen)
        option = request.options[-1]
        assert isinstance(option.payload, dict)
        selected = option.payload["model_instance_id"]
        assert isinstance(selected, str)
        chosen.append(selected)
        effect, request = apply_healing_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=rules,
            effect=effect,
            result=DecisionResult.for_request(
                result_id=f"return-{len(chosen)}",
                request=request,
                selected_option_id=option.option_id,
            ),
        )
    assert len(chosen) == min(count, 2)
    assert sum(
        step.step_kind is HealingStepKind.REVIVE_MODEL_IN_RESERVES for step in effect.resolved_steps
    ) == min(count, 2)
    assert effect.is_complete()
    assert len(state.army_definitions[0].units[0].own_models) == 5
    for prior in dead:
        current = model_by_id(state=state, model_instance_id=prior.model_instance_id)
        expected = (prior.initial_wounds if full else 1) if prior.model_instance_id in chosen else 0
        assert current.current_wounds == expected
        assert replace(current, wounds_remaining=prior.wounds_remaining) == prior
