"""Per-attack choices before hit and wound dice consume their source operations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import Modifier, RollModifier
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
from warhammer40k_core.core.random_profile_values import (
    ProfileCharacteristicValue,
    RandomProfileValue,
)
from warhammer40k_core.engine.attack_modifier_snapshots import attack_modifier_snapshots
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.damage_allocation import allocation_context_for_unit, model_by_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.modifier_evaluation import ModifierEvaluationSubject, select_modifiers
from warhammer40k_core.engine.modifier_permission_context import ModifierPermissionAttackContext
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    UnitCharacteristicModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def profile_modifier_trace(value: ProfileCharacteristicValue) -> CharacteristicModifierTrace:
    if isinstance(value, RandomProfileValue):
        return CharacteristicModifierTrace(value.characteristic, value.raw, value.modifiers)
    if value.modifier_trace is not None:
        return value.modifier_trace
    return CharacteristicModifierTrace(value.characteristic, value.raw, ())


def attack_modifier_source_context(
    *,
    pool: RangedAttackPool,
    attack_context_id: str,
    source_phase: BattlePhase,
) -> dict[str, JsonValue]:
    return {
        "continuation": "attack",
        "attack_context_id": attack_context_id,
        "source_phase": source_phase.value,
        "pool": validate_json_value(pool.to_payload()),
    }


def select_hit_modifiers(
    *,
    state: GameState,
    decisions: DecisionController,
    pool: RangedAttackPool,
    attack_context_id: str,
    source_phase: BattlePhase,
    registry: RuntimeModifierRegistry,
) -> tuple[tuple[str, ...], LifecycleStatus | None]:
    from warhammer40k_core.engine.attack_sequence_hit_wound import _unit_instance_id_for_model

    unit_id = _unit_instance_id_for_model(
        state=state, model_instance_id=pool.attacker_model_instance_id
    )
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    snapshots = attack_modifier_snapshots(
        state=state,
        pool=pool,
        source_phase=source_phase,
        runtime_modifier_registry=registry,
    )
    ignored: list[str] = []
    for label, kind in (
        (
            "skill",
            ModifierIgnoreKind.BALLISTIC_SKILL_CHARACTERISTIC
            if pool.weapon_profile.skill.characteristic is Characteristic.BALLISTIC_SKILL
            else ModifierIgnoreKind.WEAPON_SKILL_CHARACTERISTIC,
        ),
        ("hit_roll", ModifierIgnoreKind.HIT_ROLL),
    ):
        operations = tuple(item.modifier for item in snapshots if item.kind == label)
        selection = select_modifiers(
            state=state,
            decisions=decisions,
            ability_index=registry.modifier_permission_index(unit.owner_player_id),
            occurrence_id=f"{attack_context_id}:{label}",
            subject=ModifierEvaluationSubject(
                unit_id, kind, pool.attacker_model_instance_id, pool.weapon_profile_id
            ),
            modifiers=operations,
            attack_context=ModifierPermissionAttackContext(
                attacking_unit_instance_id=unit_id,
                attacker_model_instance_id=pool.attacker_model_instance_id,
                target_unit_instance_id=pool.target_unit_instance_id,
                subject_role="attacker",
                source_phase=source_phase,
                weapon_profile=pool.weapon_profile,
                attack_strength=None,
                target_toughness=None,
            ),
            source_context=attack_modifier_source_context(
                pool=pool, attack_context_id=attack_context_id, source_phase=source_phase
            ),
        )
        if selection.pending_status is not None:
            return (), selection.pending_status
        ignored.extend(f"{label}:{identifier}" for identifier in selection.ignored_modifier_ids)
    return tuple(sorted(ignored)), None


@dataclass(frozen=True, slots=True)
class WoundModifierEvaluation:
    pool: RangedAttackPool
    toughness: int
    modifier: int
    pending_status: LifecycleStatus | None = None


def select_wound_modifiers(
    *,
    state: GameState,
    decisions: DecisionController,
    pool: RangedAttackPool,
    attack_context_id: str,
    source_phase: BattlePhase,
    registry: RuntimeModifierRegistry,
) -> WoundModifierEvaluation:
    from warhammer40k_core.engine.attack_sequence_hit_wound import _unit_instance_id_for_model
    from warhammer40k_core.engine.weapon_abilities import LANCE_RULE_ID

    unit_id = _unit_instance_id_for_model(
        state=state, model_instance_id=pool.attacker_model_instance_id
    )
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    source_context = attack_modifier_source_context(
        pool=pool, attack_context_id=attack_context_id, source_phase=source_phase
    )
    strength = profile_modifier_trace(pool.weapon_profile.strength)
    selection = select_modifiers(
        state=state,
        decisions=decisions,
        ability_index=registry.modifier_permission_index(unit.owner_player_id),
        occurrence_id=f"{attack_context_id}:strength",
        subject=ModifierEvaluationSubject(
            unit_id,
            ModifierIgnoreKind.STRENGTH_CHARACTERISTIC,
            pool.attacker_model_instance_id,
            pool.weapon_profile_id,
        ),
        modifiers=strength.modifiers,
        source_context=source_context,
        attack_context=ModifierPermissionAttackContext(
            attacking_unit_instance_id=unit_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=pool.target_unit_instance_id,
            subject_role="attacker",
            source_phase=source_phase,
            weapon_profile=pool.weapon_profile,
            attack_strength=None,
            target_toughness=None,
        ),
    )
    if selection.pending_status is not None:
        return WoundModifierEvaluation(pool, 0, 0, selection.pending_status)
    if strength.modifiers:
        selected_strength = replace(strength, ignored_modifier_ids=selection.ignored_modifier_ids)
        pool = replace(
            pool, weapon_profile=replace(pool.weapon_profile, strength=selected_strength.value())
        )
    allocation = allocation_context_for_unit(
        state=state, target_unit_instance_id=pool.target_unit_instance_id
    )
    target = rules_unit_view_by_id(state=state, unit_instance_id=pool.target_unit_instance_id)
    model_ids = allocation.attached_unit_bodyguard_model_ids or allocation.alive_model_ids
    toughness_values: list[int] = []
    for model_id in model_ids:
        value = model_by_id(state=state, model_instance_id=model_id).characteristic(
            Characteristic.TOUGHNESS
        )
        trace = profile_modifier_trace(value)
        runtime_context = UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=target.unit_instance_id,
            characteristic=Characteristic.TOUGHNESS,
            base_value=trace.source_value,
            current_value=value.final,
            model_instance_id=model_id,
        )
        operations: tuple[Modifier, ...] = (
            *trace.modifiers,
            *registry.unit_characteristic_operations(runtime_context),
        )
        selection = select_modifiers(
            state=state,
            decisions=decisions,
            ability_index=registry.modifier_permission_index(target.owner_player_id),
            occurrence_id=f"{attack_context_id}:toughness:{model_id}",
            subject=ModifierEvaluationSubject(
                target.unit_instance_id, ModifierIgnoreKind.TOUGHNESS_CHARACTERISTIC, model_id
            ),
            modifiers=operations,
            source_context={**source_context, "source_value": trace.source_value},
            attack_context=ModifierPermissionAttackContext(
                attacking_unit_instance_id=unit_id,
                attacker_model_instance_id=pool.attacker_model_instance_id,
                target_unit_instance_id=pool.target_unit_instance_id,
                subject_role="target",
                source_phase=source_phase,
                weapon_profile=pool.weapon_profile,
                attack_strength=pool.weapon_profile.strength_for_interaction(),
                target_toughness=None,
            ),
        )
        if selection.pending_status is not None:
            return WoundModifierEvaluation(pool, 0, 0, selection.pending_status)
        toughness_values.append(
            CharacteristicModifierTrace(
                Characteristic.TOUGHNESS,
                trace.source_value,
                operations,
                ignored_modifier_ids=selection.ignored_modifier_ids,
            )
            .resolve()
            .final
        )
    toughness = max(toughness_values)
    wound_operations = registry.wound_roll_modifiers(
        WoundRollModifierContext(
            state=state,
            source_phase=source_phase,
            attacking_unit_instance_id=unit_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=pool.target_unit_instance_id,
            weapon_profile=pool.weapon_profile,
            strength=pool.weapon_profile.strength_for_interaction(),
            toughness=toughness,
        )
    )
    if LANCE_RULE_ID in pool.targeting_rule_ids:
        wound_operations = (
            RollModifier(modifier_id=LANCE_RULE_ID, source_id=LANCE_RULE_ID, operand=1),
            *wound_operations,
        )
    roll_selection = select_modifiers(
        state=state,
        decisions=decisions,
        ability_index=registry.modifier_permission_index(unit.owner_player_id),
        occurrence_id=f"{attack_context_id}:wound-roll",
        subject=ModifierEvaluationSubject(
            unit_id,
            ModifierIgnoreKind.WOUND_ROLL,
            pool.attacker_model_instance_id,
            pool.weapon_profile_id,
        ),
        modifiers=wound_operations,
        attack_context=ModifierPermissionAttackContext(
            attacking_unit_instance_id=unit_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=pool.target_unit_instance_id,
            subject_role="attacker",
            source_phase=source_phase,
            weapon_profile=pool.weapon_profile,
            attack_strength=pool.weapon_profile.strength_for_interaction(),
            target_toughness=toughness,
        ),
        source_context={
            **source_context,
            "strength": pool.weapon_profile.strength_for_interaction(),
            "toughness": toughness,
        },
    )
    return WoundModifierEvaluation(
        pool,
        toughness,
        sum(item.operand for item in roll_selection.modifiers),
        roll_selection.pending_status,
    )
