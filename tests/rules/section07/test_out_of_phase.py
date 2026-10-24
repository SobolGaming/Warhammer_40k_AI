"""Normal Heavy benefits disappear at real shooting consumers outside their phase."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import scenario
from tests.support.section07_fixtures import boundary_state
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.shooting_declaration_validation import (
    _apply_phase13d_weapon_modifiers,
)
from warhammer40k_core.engine.phases.shooting_model import OutOfPhaseShootingState, ShootingType
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.weapon_abilities import HEAVY_RULE_ID


@pytest.mark.parametrize("phase", [BattlePhase.MOVEMENT, BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("reaction", [False, True])
def test_actual_weapon_modifier_consumer_suppresses_phase_locked_heavy(
    section07_definitions: Section02Definitions, phase: BattlePhase, reaction: bool
) -> None:
    d = section07_definitions
    state = boundary_state(d, phase=phase, datasheet_id="000000592")
    unit = state.army_definitions[0].units[0]
    target = state.army_definitions[1].units[0]
    profile = next(
        profile
        for wargear in d.package.army_catalog.wargear
        if wargear.wargear_id.startswith("000000592:")
        for profile in wargear.weapon_profiles
        if WeaponKeyword.HEAVY in profile.keywords
    )
    assert WeaponKeyword.HEAVY in profile.keywords
    # A real native weapon definition feeds the production modifier consumer.
    # Reaction provenance is a labeled source-outcome checkpoint, not a grant.
    out_of_phase = (
        OutOfPhaseShootingState(
            battle_round=1,
            player_id="owner",
            parent_phase=phase,
            source_rule_id="constructed:section07:shoot-permission",
            source_decision_request_id="permission-request",
            source_decision_result_id="permission-result",
            source_context={},
            selected_unit_instance_id=unit.unit_instance_id,
        )
        if reaction
        else None
    )
    attacks, rule_ids, modifier = _apply_phase13d_weapon_modifiers(
        state=state,
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
        target_rules_unit=rules_unit_view_by_id(
            state=state, unit_instance_id=target.unit_instance_id
        ),
        weapon_profile=profile,
        shooting_type=ShootingType.NORMAL,
        base_attacks=1,
        base_targeting_rule_ids=(),
        base_hit_roll_modifier=0,
        target_within_half_range=False,
        terrain_features=(),
        out_of_phase_state=out_of_phase,
    )
    expected = int(phase is BattlePhase.SHOOTING and not reaction)
    assert modifier == expected
    assert (HEAVY_RULE_ID in rule_ids) is bool(expected)
    assert attacks == 1
