"""Return a native Leader within an explicitly constructed Core attachment contract."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import EnhancementAssignment
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.healing import (
    HealingEffect,
    HealingStepKind,
    apply_healing_model_decision,
    resolve_healing_until_blocked,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_strength_inventory import (
    starting_strength_records_for_army,
)


@pytest.mark.parametrize("role", ["leader", "support"])
def test_01_02_03_return_retains_attachment_equipment_and_enhancement_identity(
    section01_definitions: Section02Definitions,
    role: str,
) -> None:
    body = section01_definitions.unit(identity="body")
    leader = section01_definitions.unit(LORD_EXULTANT, identity="leader")
    original = leader.own_models[0]
    leader = replace(leader, own_models=(replace(original, wounds_remaining=0),))
    state = minimal_state(section01_definitions, body, leader)
    formation = AttachedUnitFormation(
        "attached-unit:section02:revival",
        body.unit_instance_id,
        (leader.unit_instance_id,) if role == "leader" else (),
        support_unit_instance_ids=(leader.unit_instance_id,) if role == "support" else (),
        component_unit_instance_ids=tuple(sorted((body.unit_instance_id, leader.unit_instance_id))),
        source_id="constructed:Core-attachment",
        attachment_source_ids=(f"constructed:Core-{role}-permission",),
    )
    assignment = EnhancementAssignment(
        original.model_profile_id,
        1,
        "constructed:identity-only-enhancement",
        "leader",
        "constructed:Core-enhancement-retention",
    )
    army = replace(
        state.army_definitions[0],
        attached_units=(formation,),
        enhancement_assignments=(assignment,),
    )
    state.army_definitions[:] = [army]
    state.starting_strength_records[:] = starting_strength_records_for_army(army)
    from warhammer40k_core.engine.reserves import (
        ReserveDestructionTimingPolicy,
        ReserveKind,
        ReserveOrigin,
        ReserveState,
    )

    state.record_reserve_state(
        ReserveState(
            "owner",
            formation.attached_unit_instance_id,
            ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            ReserveKind.STRATEGIC_RESERVES,
            "declare_battle_formations",
            None,
            None,
            ReserveDestructionTimingPolicy.core_rules_default(),
        )
    )
    state.record_battlefield_state(
        BattlefieldRuntimeState(
            "return", 60, 44, (), removed_model_ids=(original.model_instance_id,)
        )
    )
    effect = HealingEffect(
        "return",
        formation.attached_unit_instance_id,
        1,
        "opponent",
        source_rule_id="constructed:Core-return",
        source_context={
            "revive_destroyed_models_only": True,
            "revive_model_full_health": True,
        },
    )
    controller = DecisionController()
    rules = RulesetDescriptor.warhammer_40000_eleventh()
    effect, request = resolve_healing_until_blocked(
        state=state, decisions=controller, ruleset_descriptor=rules, effect=effect
    )
    assert request is not None
    assert isinstance(request.payload, dict)
    assert request.payload["legal_model_ids"] == [original.model_instance_id]
    effect, request = apply_healing_model_decision(
        state=state,
        decisions=controller,
        ruleset_descriptor=rules,
        effect=effect,
        result=DecisionResult.for_request(
            result_id="chosen",
            request=request,
            selected_option_id=request.options[0].option_id,
        ),
    )
    assert request is None
    assert effect.resolved_steps[0].step_kind is HealingStepKind.REVIVE_MODEL_IN_RESERVES
    current = rules_unit_view_by_id(
        state=state, unit_instance_id=formation.attached_unit_instance_id
    )
    assert current.attached_unit == formation
    assert current.component_unit_for_model(original.model_instance_id).own_models == (original,)
    assert state.army_definitions[0].enhancement_assignments == (assignment,)
    assert len(current.alive_models()) == 6
