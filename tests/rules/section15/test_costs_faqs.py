"""15.01.01, FAQ36/42/45: constructed cost grants at the native consumer boundary."""

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section15_fixtures import binding, checkpoint, context, obj, offer, record
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
from warhammer40k_core.engine.decision_request import PARAMETERIZED_DECISION_OPTION_ID
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.stratagem_cost_modifiers import (
    StratagemCostModifierBinding,
    StratagemCostModifierContext,
    StratagemCostModifierRegistry,
)
from warhammer40k_core.engine.stratagems import (
    StratagemTargetProposal,
    apply_stratagem_target_proposal,
    invalid_stratagem_target_proposal_status,
)
from warhammer40k_core.engine.stratagems_selection import _selected_command_point_cost_result
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


def half(context: StratagemCostModifierContext) -> ModifierTerm:
    """Explicit constructed permission; not attributed to the subject datasheet."""
    return ModifierTerm(ModifierOperation.DIVIDE, 2)


def increase(context: StratagemCostModifierContext) -> ModifierTerm:
    return ModifierTerm(ModifierOperation.ADD, 1)


def discount(context: StratagemCostModifierContext) -> ModifierTerm:
    return ModifierTerm(ModifierOperation.SUBTRACT, 4)


@pytest.mark.parametrize(("mode", "expected"), [("leap_to_defend", 1), ("into_the_fray", 1)])
def test_faq45_optional_section_is_original_cost_before_division(
    section15_definitions: Section02Definitions, mode: str, expected: int
) -> None:
    d = section15_definitions
    unit = d.unit()
    state = minimal_state(d, unit)
    ctx = context(state, TimingTriggerKind.END_PHASE)
    rec = record("heroic-intervention")
    registry = StratagemCostModifierRegistry.from_bindings(
        (StratagemCostModifierBinding("constructed:s15:half", "constructed:s15:permission", half),)
    )
    cost = _selected_command_point_cost_result(
        state=state,
        definition=rec.definition,
        context=ctx,
        target_binding=binding(unit.unit_instance_id),
        effect_selection={"mode": mode},
        stratagem_cost_modifier_registry=registry,
    )
    # Into the Fray is ceil((1+1)/2)=1, not ceil(1/2)+1=2.
    assert cost.command_point_cost == expected
    assert cost.modifier_ids == ("constructed:s15:half",)
    assert cost.source_ids == ("constructed:s15:permission",)


def test_cost_floor_and_usage_local_modification_leave_next_use_unmodified(
    section15_definitions: Section02Definitions,
) -> None:
    unit = section15_definitions.unit()
    state = minimal_state(section15_definitions, unit)
    definition = record("epic-challenge").definition
    ctx = context(state, TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT)
    registry = StratagemCostModifierRegistry.from_bindings(
        (
            StratagemCostModifierBinding(
                "constructed:s15:discount", "constructed:s15:permission", discount
            ),
        )
    )
    before = state.to_payload()

    def cost(registry: StratagemCostModifierRegistry | None = None) -> int:
        return _selected_command_point_cost_result(
            state=state,
            definition=definition,
            context=ctx,
            target_binding=binding(unit.unit_instance_id),
            effect_selection=None,
            stratagem_cost_modifier_registry=registry,
        ).command_point_cost

    assert cost(registry) == 0
    assert cost() == 1
    assert definition.command_point_cost == 1
    assert state.to_payload() == before


@pytest.mark.parametrize("cp", [1, 2])
def test_faq36_and_42_selected_cost_increase_resolves_or_counts_used_without_effects(
    section15_definitions: Section02Definitions, cp: int
) -> None:
    d = section15_definitions
    session, state, unit, _ = checkpoint(d, cp=cp)
    own = state.army_definition_for_player("owner")
    assert own is not None
    mid = own.unit_by_id(unit).own_model_ids()[0]
    ctx = context(
        state,
        TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
        {"selected_unit_instance_id": unit},
    )
    req = offer(session, state, "epic-challenge", ctx)
    assert isinstance(req.payload, dict)
    proposal = StratagemTargetProposal.from_payload(
        obj(req.payload)["proposal_request"]
    ).with_binding(binding(unit), effect_selection={"character_model_instance_id": mid})
    result = DecisionResult(
        "s15:accepted-cost-increase",
        req.request_id,
        req.decision_type,
        req.actor_id,
        PARAMETERIZED_DECISION_OPTION_ID,
        validate_json_value({"proposal": proposal.to_payload()}),
    )
    registry = StratagemCostModifierRegistry.from_bindings(
        (
            StratagemCostModifierBinding(
                "constructed:s15:increase", "constructed:s15:permission", increase
            ),
        )
    )
    decisions = session.lifecycle.decision_controller
    initial_effects = tuple(state.persisting_effects)
    invalid = invalid_stratagem_target_proposal_status(
        state=state,
        request=req,
        result=result,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=d.package.army_catalog,
        decisions=decisions,
        stratagem_cost_modifier_registry=registry,
    )
    assert (invalid is None) is (cp == 2)
    if invalid is not None:
        assert invalid.payload == {"invalid_reason": "insufficient_command_points"}
    # This is the same engine-owned conversion used after a selected cost choice.
    # The permission itself is constructed; no native cost-provider admission claim.
    decisions.submit_result(result)
    used = apply_stratagem_target_proposal(
        state=state,
        result=result,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=d.package.army_catalog,
        stratagem_cost_modifier_registry=registry,
        resolve_unaffordable_cost_increase_as_used=True,
    )
    assert used.command_point_cost == 2
    assert used.effects_resolved is (cp == 2)
    assert state.command_point_total("owner") == (1 if cp == 1 else 0)
    assert len(state.persisting_effects) == len(initial_effects) + int(cp == 2)
    assert tuple(state.persisting_effects[: len(initial_effects)]) == initial_effects
    assert (
        used.command_point_transaction_id is not None
        if cp == 2
        else used.command_point_transaction_id is None
    )
    assert state.stratagem_use_records == [used]
    from warhammer40k_core.engine.stratagems_eligibility import _restriction_violation

    assert (
        _restriction_violation(
            state=state,
            player_id="owner",
            definition=record("epic-challenge").definition,
            context=ctx,
            target_binding=binding(unit),
        )
        == "same_stratagem_per_phase"
    )
