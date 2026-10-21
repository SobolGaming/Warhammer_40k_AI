"""Aura clauses use real physical geometry and shared live execution."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import add_unit
from tests.support.section22_fixtures import LORD, context, pair, relocate, rule
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.rule_execution import RuleExecutionStatus, execute_rule_ir
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("a friendly", (True, False)),
        ("an enemy", (False, True)),
        ("another friendly", (False, False)),
        ("a", (True, True)),
    ],
)
@pytest.mark.parametrize("nearby", [False, True])
def test_aura_self_allegiance_and_physical_range(
    section22_definitions: Section02Definitions,
    subject: str,
    expected: tuple[bool, bool],
    nearby: bool,
) -> None:
    state, source, target = pair(section22_definitions)
    relocate(state, target, 14 if nearby else 30)
    ir = rule(
        f'Aura: while {subject} unit is within 6" of this model, subtract 1 from wound rolls.'
    )
    result = execute_rule_ir(rule_ir=ir, context=context(state, source))
    assert result.status is RuleExecutionStatus.APPLIED
    ids = result.aura_evaluations[0]["affected_unit_instance_ids"]
    assert isinstance(ids, list)
    assert (source.unit_instance_id in ids) is expected[0]
    assert (target.unit_instance_id in ids) is (expected[1] and nearby)


@pytest.mark.parametrize("anchor", ["model", "unit"])
def test_actual_anchor_moves_range_without_visibility_requirement(
    section22_definitions: Section02Definitions, anchor: str
) -> None:
    state, source, target = pair(section22_definitions)
    # Target remains fixed; moving the actual source changes range.
    ir = rule(
        f'Aura: while an enemy unit is within 6" of this {anchor}, subtract 1 from wound rolls.'
    )
    before = execute_rule_ir(rule_ir=ir, context=context(state, source))
    assert before.aura_evaluations[0]["affected_unit_instance_ids"] == []
    relocate(state, source, 14)
    after = execute_rule_ir(rule_ir=ir, context=context(state, source))
    assert after.aura_evaluations[0]["affected_unit_instance_ids"] == [target.unit_instance_id]


def test_overlapping_sources_keep_identity_and_distinct_effects(
    section22_definitions: Section02Definitions,
) -> None:
    from warhammer40k_core.engine.effects import EffectExpiration, generic_rule_persisting_effect
    from warhammer40k_core.engine.rules_unit_effects import rules_unit_persisting_effects

    state, source, target = pair(section22_definitions)
    peer = section22_definitions.unit(LORD, identity="peer")
    add_unit(state, peer, (Pose.at(13, 10),))
    log = EventLog()
    first = rule(
        'Aura: while a friendly unit is within 6" of this model, subtract 1 from wound rolls.',
        identity="first",
    )
    second = rule(
        'Aura: while a friendly unit is within 6" of this model, add 1 to hit rolls.',
        identity="second",
    )
    payloads: list[dict[str, JsonValue]] = []
    for ir, bearer in ((first, source), (first, peer), (second, peer)):
        ctx = context(state, bearer, log)
        result = execute_rule_ir(rule_ir=ir, context=ctx)
        assert result.status is RuleExecutionStatus.APPLIED
        for payload in result.effect_payloads:
            effect = generic_rule_persisting_effect(
                effect_id=f"s22:aura:{len(payloads)}",
                source_rule_id=ir.source_id,
                owner_player_id="owner",
                target_unit_instance_ids=(source.unit_instance_id,),
                started_battle_round=1,
                started_phase=state.current_battle_phase,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload=payload,
            )
            state.record_persisting_effect(effect)
            payloads.append(payload)
    effects = rules_unit_persisting_effects(state, source.unit_instance_id)
    assert len(state.persisting_effects) == 3
    assert len(effects) == 2
    assert len(payloads) == 3
    assert len(log.records) == 3
    # Shared query deduplicates same Aura while retaining different Aura identity.
    assert len(state.persisting_effects_for_unit(source.unit_instance_id)) == 2
    from warhammer40k_core.engine.generic_rule_attack_hooks import generic_rule_wound_roll_modifier
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.runtime_modifiers import WoundRollModifierContext

    attack = WoundRollModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=target.unit_instance_id,
        attacker_model_instance_id=target.own_model_ids()[0],
        target_unit_instance_id=source.unit_instance_id,
        weapon_profile=section22_definitions.weapon(f"{LORD}:bolt-pistol"),
        strength=4,
        toughness=4,
    )
    assert generic_rule_wound_roll_modifier(attack) == -1


def test_source_model_context_cannot_be_substituted(
    section22_definitions: Section02Definitions,
) -> None:
    state, source, target = pair(section22_definitions)
    ir = rule('Aura: while an enemy unit is within 6" of this model, subtract 1 from wound rolls.')
    with pytest.raises(ValueError, match="source model"):
        execute_rule_ir(
            rule_ir=ir,
            context=replace(
                context(state, source), source_model_instance_id=target.own_model_ids()[0]
            ),
        )


@pytest.mark.parametrize("off_board", ["source", "target"])
def test_off_battlefield_spatial_requirements_keep_only_own_ability(
    section22_definitions: Section02Definitions, off_board: str
) -> None:
    from warhammer40k_core.engine.reserves import (
        ReserveDestructionTimingPolicy,
        ReserveKind,
        ReserveOrigin,
        ReserveState,
    )

    state, source, target = pair(section22_definitions)
    relocate(state, target, 14)
    unit = source if off_board == "source" else target
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.without_unit_placement(unit.unit_instance_id)
    )
    state.record_reserve_state(
        ReserveState(
            "owner" if off_board == "source" else "opponent",
            unit.unit_instance_id,
            ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            ReserveKind.STRATEGIC_RESERVES,
            "declare_battle_formations",
            None,
            None,
            ReserveDestructionTimingPolicy.core_rules_default(),
        )
    )
    ir = rule('Aura: while a unit is within 6" of this model, subtract 1 from wound rolls.')
    result = execute_rule_ir(rule_ir=ir, context=context(state, source))
    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [source.unit_instance_id]


@pytest.mark.parametrize("retained", [False, True])
def test_destroyed_aura_source_requires_explicit_retained_battlefield_presence(
    section22_definitions: Section02Definitions, retained: bool
) -> None:
    from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture
    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

    state, source, target = pair(section22_definitions)
    relocate(state, target, 14)
    assert state.battlefield_state is not None
    saved = state.battlefield_state.model_placement_by_id(source.own_model_ids()[0])
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=source.unit_instance_id,
        model_instance_id=source.own_model_ids()[0],
        damage=source.own_models[0].current_wounds,
        damage_kind=DamageKind.NORMAL,
        remove_destroyed_model=not retained,
    )
    if retained:
        retain_destroyed_model_for_fixture(
            state=state,
            placement=saved,
            effect_id="constructed:s22:fod",
            source_rule_id="constructed:s22:fod",
            source_phase=BattlePhase.COMMAND,
            decisions=DecisionController(),
        )
    ir = rule('Aura: while an enemy unit is within 6" of this model, subtract 1 from wound rolls.')
    if retained:
        result = execute_rule_ir(rule_ir=ir, context=context(state, source))
        assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [target.unit_instance_id]
    else:
        with pytest.raises(GameLifecycleError, match="active ability presence"):
            execute_rule_ir(rule_ir=ir, context=context(state, source))
