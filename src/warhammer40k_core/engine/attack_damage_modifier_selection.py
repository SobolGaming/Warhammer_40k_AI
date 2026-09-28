"""Source-preserving Damage selections shared by normal and mortal attacks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import Modifier, ModifierOperation, ModifierTerm, RollModifier
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
from warhammer40k_core.core.weapon_profiles import DamageProfile, WeaponProfile
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.damage_allocation import SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.modifier_evaluation import (
    ModifierEvaluationResult,
    ModifierEvaluationSubject,
    select_modifiers,
)
from warhammer40k_core.engine.modifier_permission_context import ModifierPermissionAttackContext
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.weapon_abilities import MELTA_RULE_ID

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def damage_characteristic_operations(
    profile: DamageProfile, *, melta_bonus: int
) -> tuple[Modifier, ...]:
    if type(melta_bonus) is not int or melta_bonus < 0:
        raise GameLifecycleError("Melta damage bonus must be a non-negative integer.")
    if melta_bonus == 0:
        return profile.modifiers
    return (
        *profile.modifiers,
        ModifierTerm(ModifierOperation.ADD, melta_bonus).bind(
            modifier_id=MELTA_RULE_ID,
            source_id=MELTA_RULE_ID,
            characteristic=Characteristic.DAMAGE,
        ),
    )


def select_attack_damage_modifiers[T: Modifier | RollModifier](
    *,
    state: GameState,
    decisions: DecisionController,
    registry: RuntimeModifierRegistry,
    modifiers: tuple[T, ...],
    kind: ModifierIgnoreKind,
    stage: str,
    attack_context_id: str,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str,
    attacker_player_id: str,
    target_unit_instance_id: str,
    weapon_profile: WeaponProfile,
    attack_strength: int | None,
    target_toughness: int | None,
    source_phase: BattlePhase,
    allocated_model_instance_id: str | None,
) -> ModifierEvaluationResult[T]:
    return select_modifiers(
        state=state,
        decisions=decisions,
        ability_index=registry.modifier_permission_index(attacker_player_id),
        occurrence_id=f"{attack_context_id}:{stage}",
        subject=ModifierEvaluationSubject(
            attacking_unit_instance_id,
            kind,
            attacker_model_instance_id,
            weapon_profile.profile_id,
        ),
        modifiers=modifiers,
        attack_context=ModifierPermissionAttackContext(
            attacking_unit_instance_id=attacking_unit_instance_id,
            attacker_model_instance_id=attacker_model_instance_id,
            target_unit_instance_id=target_unit_instance_id,
            subject_role="attacker",
            source_phase=source_phase,
            weapon_profile=weapon_profile,
            attack_strength=attack_strength,
            target_toughness=target_toughness,
        ),
        source_context={
            "continuation": "attack",
            "evaluation_stage": stage,
            "attack_context_id": attack_context_id,
            "source_phase": source_phase.value,
            "target_unit_instance_id": target_unit_instance_id,
            "allocated_model_instance_id": allocated_model_instance_id,
        },
    )


def damage_value_from_operations(source: int, modifiers: tuple[Modifier, ...]) -> int:
    return CharacteristicModifierTrace(Characteristic.DAMAGE, source, modifiers).resolve().final


def allocated_damage_characteristic_operations(
    modifiers: tuple[RollModifier, ...],
) -> tuple[Modifier, ...]:
    operations: list[Modifier] = []
    for modifier in modifiers:
        if modifier.source_id is None:
            raise GameLifecycleError("Allocated Damage operation requires its source.")
        operations.append(
            ModifierTerm(ModifierOperation.ADD, modifier.operand).bind(
                modifier_id=modifier.modifier_id,
                source_id=modifier.source_id,
                characteristic=Characteristic.DAMAGE,
            )
        )
    return tuple(operations)


def retained_damage_allocation_model(
    *,
    decisions: DecisionController,
    attack_context_id: str,
    save_die: JsonValue,
) -> str | None:
    """Resume the accepted model selection when a later modifier choice paused it."""
    matches: list[str] = []
    for record in decisions.records:
        if record.request.decision_type != SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE:
            continue
        row = record.request.payload
        if not isinstance(row, dict) or not isinstance(row.get("attack_context"), dict):
            raise GameLifecycleError("Recorded damage allocation context is malformed.")
        context = row["attack_context"]
        assert isinstance(context, dict)
        if context.get("attack_context_id") != attack_context_id:
            continue
        if canonical_json(row["save_die"]) != canonical_json(save_die):
            raise GameLifecycleError("Recorded damage allocation save die drifted.")
        matches.append(record.result.selected_option_id)
    if len(matches) > 1:
        raise GameLifecycleError("Damage allocation model was selected more than once.")
    return None if not matches else matches[0]
