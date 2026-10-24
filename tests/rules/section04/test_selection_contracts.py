"""Explicit Core contracts for combinations absent from retained native profiles."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section04_fixtures import combat_state
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.shooting_declaration_validation import (
    _validate_model_pistol_exclusivity,
)
from warhammer40k_core.engine.phases.shooting_requests import (
    request_out_of_phase_shooting_declaration,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID
from warhammer40k_core.engine.weapon_declaration import WeaponDeclaration
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model


@pytest.mark.parametrize("close_quarters_first", [False, True])
@pytest.mark.parametrize("mixed", [False, True])
def test_constructed_close_quarters_sidearm_exclusivity(
    section04_definitions: Section02Definitions, close_quarters_first: bool, mixed: bool
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    state = combat_state(d, unit)
    physical = equipped_weapon_profile_instances_for_model(
        model=unit.own_models[0], army_catalog=d.package.army_catalog
    )[:2]
    selected: dict[tuple[str, str], bool] = {}
    for index, instance in enumerate(physical):
        cq = close_quarters_first if index == 0 or not mixed else not close_quarters_first
        # Explicit Core CLOSE-QUARTERS contract, not a native datasheet claim.
        profile = replace(
            instance.weapon_profile, keywords=(WeaponKeyword.CLOSE_QUARTERS,) if cq else ()
        )
        declaration = WeaponDeclaration(
            instance.weapon_instance_id,
            instance.model_instance_id,
            instance.wargear_id,
            profile.profile_id,
            "enemy:target",
            ShootingType.NORMAL,
        )
        result = _validate_model_pistol_exclusivity(
            state=state,
            selected_unit=unit,
            declaration=declaration,
            weapon_profile=profile,
            model_pistol_declaration_kind=selected,
            proposal_request_id="constructed:sidearms",
        )
        if index == 1 and mixed:
            assert result is not None
            assert (
                result.violations[0].violation_code
                == "mixed_close_quarters_non_close_quarters_declaration"
            )
        else:
            assert result is None
    assert selected[(unit.unit_instance_id, unit.own_model_ids()[0])] is close_quarters_first


def test_rule_chosen_native_unit_gets_out_of_phase_attack_selection(
    section04_definitions: Section02Definitions,
) -> None:
    d = section04_definitions
    unit = d.unit(LORD_EXULTANT)
    state = combat_state(d, unit, phase=BattlePhase.MOVEMENT)
    state.active_player_id = "opponent"
    decisions = DecisionController()
    status = request_out_of_phase_shooting_declaration(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=d.package.army_catalog,
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
        parent_phase=BattlePhase.MOVEMENT,
        source_rule_id=FIRE_OVERWATCH_RULE_ID,
        source_decision_request_id="contract:rule-choice",
        source_decision_result_id="contract:rule-result",
        source_context={"triggering_enemy_unit_instance_id": "enemy:target"},
        target_unit_ids=("enemy:target",),
    )
    assert state.out_of_phase_shooting_state is not None
    assert state.out_of_phase_shooting_state.selected_unit_instance_id == unit.unit_instance_id
    assert state.out_of_phase_shooting_state.source_rule_id == FIRE_OVERWATCH_RULE_ID
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "submit_shooting_declaration"
    assert any(e.event_type == "out_of_phase_shooting_started" for e in decisions.event_log.records)
    assert not any(e.event_type == "attack_sequence_step" for e in decisions.event_log.records)
    assert state.current_battle_phase is BattlePhase.MOVEMENT
