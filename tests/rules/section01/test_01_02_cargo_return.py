"""Native Aeldari model inventories, explicit Core capacity contract, real decisions."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import AVENGERS, Section02Definitions
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.healing import (
    HealingEffect,
    HealingStepKind,
    apply_healing_model_decision,
    resolve_healing_until_blocked,
)
from warhammer40k_core.engine.transports import (
    TransportCapacityProfile,
    TransportCargoState,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection


@pytest.mark.parametrize("occupied", [11, 12])
def test_01_02_03_cargo_capacity_return_or_destroy_without_triggers(
    section01_definitions: Section02Definitions, occupied: int
) -> None:
    target = section01_definitions.unit(AVENGERS, identity="returning")
    other = section01_definitions.unit(
        AVENGERS,
        identity="other-cargo",
        composition=(
            ModelProfileSelection("000000593:dire-avenger-exarch", 1),
            ModelProfileSelection("000000593:dire-avengers", 9),
        ),
    )
    carrier = section01_definitions.unit("000000599", identity="carrier")
    casualty = target.own_models[0]
    target = replace(
        target,
        own_models=tuple(
            replace(m, wounds_remaining=0) if m == casualty else m for m in target.own_models
        ),
    )
    other = replace(
        other,
        own_models=tuple(
            replace(m, wounds_remaining=0) if i >= occupied - 4 else m
            for i, m in enumerate(other.own_models)
        ),
    )
    state = minimal_state(section01_definitions, target, other, carrier)
    removed = tuple(
        m.model_instance_id for u in (target, other) for m in u.own_models if not m.is_alive
    )
    state.record_battlefield_state(
        BattlefieldRuntimeState("cargo-return", 60, 44, (), removed_model_ids=removed)
    )
    state.transport_cargo_states.append(
        TransportCargoState(
            "owner",
            carrier.unit_instance_id,
            TransportCapacityProfile(
                carrier.datasheet_id, 12, source_id="constructed:Core-capacity-12"
            ),
            (target.unit_instance_id, other.unit_instance_id),
        )
    )
    decisions = DecisionController()
    rules = RulesetDescriptor.warhammer_40000_eleventh()
    effect = HealingEffect(
        "return",
        target.unit_instance_id,
        1,
        "opponent",
        source_rule_id="constructed:Core-return",
        source_context={
            "revive_destroyed_models_only": True,
            "revive_model_full_health": True,
        },
    )
    effect, request = resolve_healing_until_blocked(
        state=state, decisions=decisions, ruleset_descriptor=rules, effect=effect
    )
    assert request is not None
    assert request.actor_id == "owner"
    assert isinstance(request.payload, dict)
    assert request.payload["legal_model_ids"] == [casualty.model_instance_id]
    effect, next_request = apply_healing_model_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=rules,
        effect=effect,
        result=DecisionResult.for_request(
            result_id="return-selected",
            request=request,
            selected_option_id=request.options[0].option_id,
        ),
    )
    assert next_request is None
    (step,) = effect.resolved_steps
    assert step.step_kind is (
        HealingStepKind.REVIVE_MODEL_EMBARKED
        if occupied < 12
        else HealingStepKind.REVIVE_MODEL_DESTROYED_NO_CAPACITY
    )
    returned = state.army_definitions[0].units[0].own_models[0]
    assert returned.wounds_remaining == (casualty.initial_wounds if occupied < 12 else 0)
    assert replace(returned, wounds_remaining=casualty.wounds_remaining) == casualty
    assert state.battlefield_state is not None
    assert state.battlefield_state.placed_model_ids() == ()
    assert not any(
        "destroy" in record.event_type or "damage" in record.event_type
        for record in decisions.event_log.records
    )
