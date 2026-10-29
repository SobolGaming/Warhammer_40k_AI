"""Parsed Core-contract grants, native profiles and exact expiration boundaries."""

import pytest

from tests.support.section01_fixtures import core_rule, minimal_state, reserve_unit
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)


@pytest.mark.parametrize(
    ("prefix", "suffix", "kind"),
    [
        ("", "", "end_phase"),
        ("In the Shooting phase, ", "", "end_phase"),
        ("In your turn, ", "", "end_turn"),
        ("Until the end of the turn, ", "", "end_turn"),
    ],
)
@pytest.mark.parametrize("offboard", ["battlefield", "reserves", "embarked"])
def test_01_02_02_parsed_lifetime_reaches_weapon_consumer(
    section01_definitions: Section02Definitions,
    prefix: str,
    suffix: str,
    kind: str,
    offboard: str,
) -> None:
    unit = section01_definitions.unit()
    state = minimal_state(section01_definitions, unit)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    rule = core_rule(
        prefix
        + "add 1 to the Attacks characteristic of ranged weapons equipped by models in this unit."
        + suffix
    )
    result = execute_rule_ir(
        rule_ir=rule,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="owner",
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            active_player_id="owner",
            source_unit_instance_id=unit.unit_instance_id,
            state=state,
        ),
    )
    assert result.status is RuleExecutionStatus.APPLIED
    (effect,) = result.created_persisting_effects
    assert effect.expiration.expiration_kind.value == kind
    if offboard == "reserves":
        reserve_unit(state, unit)
    elif offboard == "embarked":
        from warhammer40k_core.engine.transports import (
            TransportCapacityProfile,
            TransportCargoState,
        )

        carrier = section01_definitions.unit("000000599", identity="carrier")
        state.add_unit_to_army(
            player_id="owner", unit=carrier, source_id="constructed:core-carrier"
        )
        state.transport_cargo_states.append(
            TransportCargoState(
                "owner",
                carrier.unit_instance_id,
                TransportCapacityProfile(
                    carrier.datasheet_id,
                    12,
                    source_id="constructed:Core-cargo-contract",
                ),
                (unit.unit_instance_id,),
            )
        )
    weapon = section01_definitions.weapon("000004080:bolt-pistol")
    query = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        target_unit_instance_id=unit.unit_instance_id,
        weapon_profile=weapon,
    )
    assert weapon.attack_profile.fixed_attacks is not None
    registry = RuntimeModifierRegistry.empty()
    assert (
        registry.modified_weapon_profile(query).attack_profile.fixed_attacks
        == weapon.attack_profile.fixed_attacks + 1
    )
    if offboard == "reserves":
        state.reserve_states.clear()
    elif offboard == "embarked":
        state.transport_cargo_states.clear()
    assert (
        registry.modified_weapon_profile(query).attack_profile.fixed_attacks
        == weapon.attack_profile.fixed_attacks + 1
    )
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=1, phase=BattlePhase.SHOOTING, player_id="opponent"
        )
    )
    assert state.persisting_effects == [effect]
    expiration = effect.expiration
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary(
            expiration.expiration_kind,
            expiration.battle_round,
            expiration.phase,
            expiration.player_id,
        )
    )
    assert state.persisting_effects == []
    assert (
        registry.modified_weapon_profile(query).attack_profile.fixed_attacks
        == weapon.attack_profile.fixed_attacks
    )
