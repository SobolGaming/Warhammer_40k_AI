"""Inclusive leadership outcomes and their unit-wide restrictions."""

import pytest

from tests.support.section01_fixtures import minimal_state, place_units
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
    StratagemTargetPermissionStatus,
    friendly_stratagem_target_permission,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_pre_oc_ineligibility_reason,
)
from warhammer40k_core.engine.objective_control import (
    model_objective_control_characteristic,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext


@pytest.mark.parametrize("faces", [(1, 1), (2, 3), (3, 3), (3, 4), (6, 6)])
def test_01_06_07_inclusive_roll_and_failed_unit_model_restrictions(
    section01_definitions: Section02Definitions, faces: tuple[int, int]
) -> None:
    unit = section01_definitions.unit()
    state = minimal_state(section01_definitions, unit)
    place_units(state)
    context = BelowHalfStrengthContext.from_unit(
        player_id="owner",
        unit=unit,
        starting_strength=state.starting_strength_record_for_unit(unit.unit_instance_id),
        current_model_ids=unit.own_model_ids(),
    )
    request = BattleShockTestRequest.for_unit(
        request_id="forced",
        game_id=state.game_id,
        battle_round=1,
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=6,
        below_half_strength_context=context,
    )
    assert (request.spec.expression.quantity, request.spec.expression.sides) == (2, 6)
    result = BattleShockResult.from_roll_state(
        result_id="morale",
        request=request,
        roll_state=DiceRollManager("morale").roll_fixed(request.spec, faces),
    )
    passed = sum(faces) >= 6
    assert result.passed is passed
    state.record_battle_shock_result(result)
    assert state.battle_shocked_unit_ids == ([] if passed else [unit.unit_instance_id])
    if not passed:
        assert set(state.battle_shocked_unit_states[0].model_instance_ids) == set(
            unit.own_model_ids()
        )
    for model in unit.own_models:
        value = model_objective_control_characteristic(model, battle_shocked=not passed)
        assert value.is_numeric is passed
    for player in ("owner", "opponent"):
        permission = friendly_stratagem_target_permission(
            player_id=player,
            target_player_id="owner",
            target_unit_instance_id=unit.unit_instance_id,
            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
        )
        assert permission.status is (
            StratagemTargetPermissionStatus.DENIED
            if not passed and player == "owner"
            else StratagemTargetPermissionStatus.ALLOWED
        )
    assert mission_action_pre_oc_ineligibility_reason(
        state=state,
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    ) == (None if passed else "mission_action_unit_battle_shocked")
