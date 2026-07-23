from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.attack_sequence_geometry_targets import _damage_value
from warhammer40k_core.engine.attack_sequence_hit_wound import (
    _devastating_wounds_resolution_for_attack,
    _emit_event,
    _melta_damage_modifier,
)
from warhammer40k_core.engine.attack_sequence_model import (
    AttackResolutionContextPayload,
    AttackSequenceEvent,
    AttackSequenceHooks,
    AttackSequenceStep,
)
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.deferred_mortal_wounds import DeferredMortalWounds
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.weapon_abilities import (
    DEVASTATING_WOUNDS_RULE_ID,
    DevastatingWoundsResolution,
    has_weapon_keyword,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex


def defer_grouped_devastating_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    wounded_contexts: tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    hooks: AttackSequenceHooks,
    stratagem_index: StratagemCatalogIndex | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
    precision_priority_model_ids: tuple[str, ...],
) -> tuple[
    AttackSequence,
    tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    LifecycleStatus | None,
]:
    current = attack_sequence
    normal_contexts: list[tuple[AttackSequence, AttackResolutionContextPayload]] = []
    pool = attack_sequence.current_pool()
    for wounded_sequence, attack_context in wounded_contexts:
        target_keywords = rules_unit_view_by_id(
            state=state,
            unit_instance_id=attack_context["target_unit_instance_id"],
        ).keywords
        resolution = _devastating_wounds_resolution_for_attack(
            pool=pool,
            attack_context=attack_context,
            target_keywords=target_keywords,
        )
        if resolution is not DevastatingWoundsResolution.MORTAL_WOUNDS:
            normal_contexts.append((wounded_sequence, attack_context))
            continue
        damage_value, status = _damage_value(
            state=state,
            decisions=decisions,
            manager=manager,
            profile=pool.weapon_profile.damage_profile,
            attack_context_id=attack_context["attack_context_id"],
            attacker_player_id=attack_sequence.attacker_player_id,
            affected_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            weapon_profile=pool.weapon_profile,
            source_phase=attack_sequence.source_phase,
            stratagem_index=stratagem_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if status is not None:
            return current, (), status
        if damage_value is None:
            raise GameLifecycleError("Damage roll did not resolve a value.")
        mortal_wounds = damage_value + _melta_damage_modifier(
            pool,
            target_keywords=target_keywords,
        )
        deferred = DeferredMortalWounds(
            source_rule_id=DEVASTATING_WOUNDS_RULE_ID,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            attack_context_id=attack_context["attack_context_id"],
            mortal_wounds=mortal_wounds,
            priority_model_ids=(
                precision_priority_model_ids
                if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.PRECISION)
                else ()
            ),
        )
        _emit_event(
            decisions=decisions,
            hooks=hooks,
            event=AttackSequenceEvent(
                step=AttackSequenceStep.DAMAGE,
                sequence_id=wounded_sequence.sequence_id,
                attack_context_id=attack_context["attack_context_id"],
                pool_index=wounded_sequence.pool_index,
                attack_index=wounded_sequence.attack_index,
                payload=validate_json_value(
                    {
                        "saving_throw": None,
                        "damage_application": None,
                        "feel_no_pain": None,
                        "deferred_mortal_wounds": deferred.to_payload(),
                    }
                ),
            ),
        )
        decisions.event_log.append(
            "devastating_wounds_deferred",
            {
                "sequence_id": attack_sequence.sequence_id,
                "attack_context_id": attack_context["attack_context_id"],
                "target_unit_instance_id": attack_context["target_unit_instance_id"],
                "mortal_wounds": mortal_wounds,
                "source_rule_id": DEVASTATING_WOUNDS_RULE_ID,
            },
        )
        current = current.with_deferred_mortal_wounds(deferred)
    return current, tuple(normal_contexts), None
