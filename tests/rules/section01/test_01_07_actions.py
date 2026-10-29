"""Native Action eligibility regression and explicit permission-contract integrity."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state, place_units
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
)
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.mission_action_battle_shock import (
    action_battle_shock_permission_sources,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_action_interruptions import (
    interrupt_mission_actions_for_battle_shock,
)


def test_01_07_battle_shock_prevents_completion_of_started_native_action(
    section01_definitions: Section02Definitions,
) -> None:
    unit = section01_definitions.unit()
    state = minimal_state(section01_definitions, unit)
    place_units(state)
    action = MissionActionState.start(
        action_id="action",
        mission_action_id="Core-action-contract",
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
        target_id="location",
        condition_target_id=None,
        mission_id="constructed:zero-VP-action",
        battle_round=1,
        phase="shooting",
        start_timing="now",
        completion_timing="end_turn",
        eligible_unit_instance_ids=(unit.unit_instance_id,),
        interruption_conditions=(),
        scoring_source_id="constructed:Core-action",
        victory_points=0,
    )
    state.mission_action_states.append(action)
    assert (
        action_battle_shock_permission_sources(state=state, unit_instance_id=unit.unit_instance_id)
        == ()
    )
    (interrupted,) = interrupt_mission_actions_for_battle_shock(
        state=state,
        decisions=None,
        shocked_unit_ids=(unit.unit_instance_id,),
        source_result_id="shock",
    )
    assert interrupted.status is MissionActionStatus.INTERRUPTED
    with pytest.raises(GameLifecycleError, match="Only started"):
        interrupted.complete_without_award(
            battle_round=1, phase="fight", completion_timing="end_turn"
        )
    with pytest.raises(GameLifecycleError, match="Battle-shocked"):
        action.complete_without_award(
            battle_round=1,
            phase="fight",
            completion_timing="end_turn",
            battle_shocked_unit_ids=(unit.unit_instance_id,),
        )
    assert (
        action.complete_without_award(
            battle_round=1, phase="fight", completion_timing="end_turn"
        ).status
        is MissionActionStatus.COMPLETED
    )


@pytest.mark.parametrize("drift", [False, True])
def test_action_permission_integrity_still_checked_for_actual_grant(
    section01_definitions: Section02Definitions, drift: bool
) -> None:
    from typing import cast

    from warhammer40k_core.core.datasheet import CatalogJsonObject
    from warhammer40k_core.rules.parsed_tokens import TextSpan
    from warhammer40k_core.rules.rule_ir import (
        RuleClause,
        RuleDuration,
        RuleDurationKind,
        RuleEffectKind,
        RuleEffectSpec,
        RuleIR,
        RuleTargetKind,
        RuleTargetSpec,
        parameters_from_pairs,
    )

    original = section01_definitions.unit()
    text = "Constructed contract: unconditional Action permission while Battle-shocked."
    span = TextSpan(text, 0, len(text))
    rule = RuleIR(
        "constructed:Action-permission",
        "constructed:Action-permission",
        text,
        "constructed-contract",
        (
            RuleClause(
                "permission",
                span,
                target=RuleTargetSpec(RuleTargetKind.THIS_UNIT, span),
                duration=RuleDuration(RuleDurationKind.PERMANENT, span),
                effects=(
                    RuleEffectSpec(
                        RuleEffectKind.GRANT_ABILITY,
                        span,
                        parameters_from_pairs(
                            (("ability", "can_perform_actions_while_battle_shocked"),)
                        ),
                    ),
                ),
            ),
        ),
    )
    descriptor = replace(
        original.datasheet_abilities[0],
        source_id="drift" if drift else rule.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
    # Explicit constructed permission boundary; no native datasheet certification.
    unit = replace(original, datasheet_abilities=(descriptor,))
    state = minimal_state(section01_definitions, unit)
    if drift:
        with pytest.raises(GameLifecycleError, match="permission source drifted"):
            action_battle_shock_permission_sources(
                state=state, unit_instance_id=unit.unit_instance_id
            )
    else:
        assert action_battle_shock_permission_sources(
            state=state, unit_instance_id=unit.unit_instance_id
        ) == (rule.source_id,)
