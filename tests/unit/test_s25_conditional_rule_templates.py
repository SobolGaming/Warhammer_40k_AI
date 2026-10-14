"""Explicit analytical source templates; these queries do not claim facade content coverage."""

from dataclasses import replace
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import battle_state

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.catalog_modifier_ignore import (
    CatalogModifierIgnorePermission,
    ModifierIgnoreKind,
    modifier_ignore_permissions_for_subject,
    modifier_ignore_templates_for_gathering,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import EffectExpiration, generic_rule_persisting_effect
from warhammer40k_core.engine.generic_rule_effect_targets import AttackRole
from warhammer40k_core.engine.modifier_permission_context import (
    ModifierPermissionAttackContext,
    UnsupportedModifierPermissionContextError,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    generic_rule_effect_payload,
)
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)


@pytest.mark.parametrize("role", ["attacker", "target"])
@pytest.mark.parametrize("model_scope", [False, True])
def test_symbolic_permission_keeps_numeric_predicate_and_nonnumeric_gates(
    role: str,
    model_scope: bool,
) -> None:
    decisions = DecisionController()
    state = battle_state(decisions=decisions)
    attacker = state.army_definitions[0].units[0]
    target = state.army_definitions[1].units[0]
    subject = attacker if role == "attacker" else target
    model = subject.own_models[0]
    profile = next(
        profile
        for gear in ArmyCatalog.phase9a_canonical_content_pack().wargear
        if gear.wargear_id == "core-bolt-rifle"
        for profile in gear.weapon_profiles
    )
    assert "core-bolt-rifle" in attacker.own_models[0].wargear_ids
    text = (
        "S25 analytical source: ignore Save-roll modifiers only in Shooting "
        "against enemy Infantry with S > T."
    )
    span = TextSpan(text, 0, len(text))
    effect = RuleEffectSpec(
        RuleEffectKind.GRANT_ABILITY,
        span,
        parameters_from_pairs(
            (
                ("ability", "modifier_ignore_permission"),
                ("selection", "any_or_all"),
                ("modifier_kinds", ("save_roll",)),
                ("attack_role", role),
                ("source_phase", "shooting"),
                ("target_required_keyword", "INFANTRY"),
                ("target_allegiance", "enemy"),
                ("target_constraint", "attack_strength_greater_than_target_toughness"),
            )
        ),
    )
    clause = RuleClause(
        "analytical:s25-numeric-permission:clause",
        span,
        trigger=RuleTrigger(RuleTriggerKind.DICE_ROLL, span),
        target=RuleTargetSpec(
            RuleTargetKind.THIS_MODEL if model_scope else RuleTargetKind.THIS_UNIT, span
        ),
        effects=(effect,),
    )
    rule = RuleIR(
        "analytical:s25-numeric-permission:rule",
        "analytical:s25-numeric-permission",
        text,
        "analytical-declared-ir",
        (clause,),
    )
    payload = generic_rule_effect_payload(
        rule_ir=rule,
        clause=clause,
        effect=effect,
        context=RuleExecutionContext(
            state.game_id,
            "player-a" if role == "attacker" else "player-b",
            state.battle_round,
            state.current_battle_phase,
            state.active_player_id,
            source_unit_instance_id=subject.unit_instance_id,
            source_model_instance_id=model.model_instance_id if model_scope else None,
            target_unit_instance_ids=(subject.unit_instance_id,),
            state=state,
        ),
        target_unit_instance_ids=(subject.unit_instance_id,),
        effect_index=0,
    )
    state.record_persisting_effect(
        generic_rule_persisting_effect(
            effect_id="analytical:s25-numeric-permission:effect",
            source_rule_id=rule.source_id,
            owner_player_id="player-a" if role == "attacker" else "player-b",
            target_unit_instance_ids=(subject.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=state.current_battle_phase,
            expiration=EffectExpiration.end_phase(
                battle_round=1, phase=BattlePhase.SHOOTING, player_id="player-a"
            ),
            effect_payload=payload,
        )
    )
    context = ModifierPermissionAttackContext(
        attacker.unit_instance_id,
        attacker.own_models[0].model_instance_id,
        target.unit_instance_id,
        cast(AttackRole, role),
        BattlePhase.SHOOTING,
        profile,
        None,
        None,
    )

    # Use explicit typed calls, not coercion or runtime context substitution.
    def templates(
        attack: ModifierPermissionAttackContext,
    ) -> tuple[CatalogModifierIgnorePermission, ...]:
        return modifier_ignore_templates_for_gathering(
            state=state,
            ability_index=AbilityCatalogIndex.from_records(()),
            unit_instance_id=subject.unit_instance_id,
            model_instance_id=model.model_instance_id,
            kind=ModifierIgnoreKind.SAVE_ROLL,
            attack_context=attack,
        )

    def permissions(
        attack: ModifierPermissionAttackContext,
    ) -> tuple[CatalogModifierIgnorePermission, ...]:
        return modifier_ignore_permissions_for_subject(
            state=state,
            ability_index=AbilityCatalogIndex.from_records(()),
            unit_instance_id=subject.unit_instance_id,
            model_instance_id=model.model_instance_id,
            kind=ModifierIgnoreKind.SAVE_ROLL,
            attack_context=attack,
        )

    before = state.to_payload()
    matches = templates(context)
    assert len(matches) == 1
    assert matches[0].rule_ir_hash == rule.ir_hash()
    assert matches[0].source_context is not None
    assert "attack_strength_greater_than_target_toughness" in str(matches[0].source_context)
    assert templates(replace(context, source_phase=BattlePhase.FIGHT)) == ()
    with pytest.raises(UnsupportedModifierPermissionContextError, match=r"Strength.*Toughness"):
        permissions(context)
    assert len(permissions(replace(context, attack_strength=6, target_toughness=4))) == 1
    assert permissions(replace(context, attack_strength=3, target_toughness=4)) == ()
    assert state.to_payload() == before
