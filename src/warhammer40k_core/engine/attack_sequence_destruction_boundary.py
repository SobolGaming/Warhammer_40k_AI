from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.attack_sequence_destruction_model import PendingAttackDestruction
from warhammer40k_core.engine.attack_sequence_model import (
    AttackResolutionContextPayload,
    AttackSequenceHooks,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, ModelPlacementPayload
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DestructionReactionSource,
    FeelNoPainResolution,
    remove_destroyed_model_from_battlefield,
)
from warhammer40k_core.engine.destruction_provenance import (
    DestructionProvenance,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_attack_sequence_2026_09,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.game_state import GameState


CORE_DESTROYED_TIMING_RULE_ID = core_attack_sequence_2026_09.DESTROYED_RULE_ID


def attack_destruction_requires_end_of_attacks_boundary(
    *,
    state: GameState,
    damage: DamageApplication | None,
) -> bool:
    if damage is None or not damage.destroyed:
        return False
    if state.destruction_reaction_sources_for_model(model_instance_id=damage.model_instance_id):
        return True
    from warhammer40k_core.engine.attack_sequence_destroyed_transport import (
        _destroyed_transport_cargo_state_for_damage,
    )

    cargo_state = _destroyed_transport_cargo_state_for_damage(state=state, damage=damage)
    return cargo_state is not None and bool(cargo_state.embarked_unit_instance_ids)


def defer_destroyed_attack_damage_if_required(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication | None,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    destroyed_model_controller_player_id: str,
    destruction_sources: tuple[DestructionReactionSource, ...],
    hooks: AttackSequenceHooks,
) -> AttackSequence | None:
    if not attack_destruction_requires_end_of_attacks_boundary(state=state, damage=damage):
        return None
    if damage is None or not damage.destroyed:
        raise GameLifecycleError("Deferred attack destruction requires destroyed damage.")
    from warhammer40k_core.engine.attack_sequence_damage_resolution import (
        _advance_after_resolved_hit,
    )
    from warhammer40k_core.engine.attack_sequence_hit_wound import (
        _destroyed_model_placement_payload,
        _emit_damage_step_event,
    )

    destroyed_model_placement = _destroyed_model_placement_payload(
        state=state,
        model_instance_id=damage.model_instance_id,
    )
    damage_event = _emit_damage_step_event(
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        damage=damage,
        saving_throw=None,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=feel_no_pain,
    )
    deferred_sequence = defer_attack_destruction_until_attacks_resolved(
        decisions=decisions,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=feel_no_pain,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        destruction_sources=destruction_sources,
        damage_event=damage_event,
        destroyed_model_placement=destroyed_model_placement,
    )
    return _advance_after_resolved_hit(
        attack_sequence=deferred_sequence,
        attack_context=attack_context,
    )


def defer_attack_destruction_until_attacks_resolved(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    destroyed_model_controller_player_id: str,
    destruction_sources: tuple[DestructionReactionSource, ...],
    damage_event: EventRecord,
    destroyed_model_placement: JsonValue,
) -> AttackSequence:
    pending = PendingAttackDestruction(
        attack_context=attack_context,
        attack_pool=attack_sequence.current_pool(),
        damage_application=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=feel_no_pain,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        destruction_sources=destruction_sources,
        damage_event_id=damage_event.event_id,
        destroyed_model_placement=destroyed_model_placement,
    )
    updated = attack_sequence.with_pending_attack_destruction(pending)
    decisions.event_log.append(
        "attack_model_destruction_deferred",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attack_context_id": attack_context["attack_context_id"],
            "model_instance_id": damage.model_instance_id,
            "target_unit_instance_id": damage.target_unit_instance_id,
            "damage_event_id": damage_event.event_id,
            "timing_rule_id": CORE_DESTROYED_TIMING_RULE_ID,
            "attack_pool_sha256": pending.attack_pool_evidence_sha256,
            "destruction_sources": [source.to_payload() for source in destruction_sources],
            "destroyed_model_placement": destroyed_model_placement,
        },
    )
    return updated


def pending_attack_destruction_damage_event(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    damage: DamageApplication,
) -> EventRecord | None:
    pending = attack_sequence.current_pending_attack_destruction
    if pending is None:
        return None
    if pending.damage_application != damage:
        return None
    matches = tuple(
        event for event in decisions.event_log.records if event.event_id == pending.damage_event_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Pending attack destruction damage event is missing.")
    event = matches[0]
    if event.event_type != "attack_sequence_step" or not isinstance(event.payload, dict):
        raise GameLifecycleError("Pending attack destruction damage event type drift.")
    nested = event.payload.get("payload")
    if (
        event.payload.get("sequence_id") != attack_sequence.sequence_id
        or event.payload.get("attack_context_id") != pending.attack_context["attack_context_id"]
        or event.payload.get("step") != "damage"
        or not isinstance(nested, dict)
        or nested.get("damage_application") != damage.to_payload()
    ):
        raise GameLifecycleError("Pending attack destruction damage event payload drift.")
    return event


def complete_current_attack_destruction_or_advance(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
) -> AttackSequence:
    pending = attack_sequence.current_pending_attack_destruction
    if pending is None:
        from warhammer40k_core.engine.attack_sequence_damage_resolution import (
            _advance_after_resolved_hit,
        )

        return _advance_after_resolved_hit(
            attack_sequence=attack_sequence,
            attack_context=attack_context,
        )
    if pending.attack_context != attack_context:
        raise GameLifecycleError("Completed attack destruction context drift.")
    return attack_sequence.without_current_pending_attack_destruction()


def resolve_pending_attack_destruction_until_blocked(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    hooks: AttackSequenceHooks,
) -> tuple[AttackSequence, LifecycleStatus | None]:
    pending = attack_sequence.current_pending_attack_destruction
    if pending is None:
        return attack_sequence, None
    if attack_sequence.attacks_resolved_event_id is None:
        raise GameLifecycleError(
            "Attack destruction reactions require attacks-resolved boundary evidence."
        )

    from warhammer40k_core.engine.attack_sequence_damage_resolution import (
        _destruction_reaction_status_if_needed,
        _resolve_mandatory_destruction_reactions_before_removal,
    )
    from warhammer40k_core.engine.attack_sequence_destroyed_transport import (
        _begin_destroyed_transport_disembark_if_needed,
    )
    from warhammer40k_core.engine.attack_sequence_hit_wound import _emit_damage_event

    updated_sequence, transport_status = _begin_destroyed_transport_disembark_if_needed(
        state=state,
        decisions=decisions,
        attack_sequence=attack_sequence,
        attack_context=pending.attack_context,
        damage=pending.damage_application,
        saving_throw_payload=pending.saving_throw_payload,
        feel_no_pain=pending.feel_no_pain,
        destroyed_model_controller_player_id=(pending.destroyed_model_controller_player_id),
        sources=pending.destruction_sources,
    )
    if (
        transport_status is not None
        or updated_sequence.pending_destroyed_transport_disembark is not None
    ):
        return updated_sequence, transport_status

    mandatory_status = _resolve_mandatory_destruction_reactions_before_removal(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=updated_sequence,
        attack_context=pending.attack_context,
        damage=pending.damage_application,
        saving_throw_payload=pending.saving_throw_payload,
        feel_no_pain=pending.feel_no_pain,
        destroyed_model_controller_player_id=(pending.destroyed_model_controller_player_id),
        sources=pending.destruction_sources,
    )
    if mandatory_status is not None:
        return updated_sequence, mandatory_status

    _validate_retained_model_placement(state=state, pending=pending)
    remove_destroyed_model_from_battlefield(
        state=state,
        model_instance_id=pending.damage_application.model_instance_id,
    )
    destroyed_emission = _emit_damage_event(
        state=state,
        decisions=decisions,
        hooks=hooks,
        attack_sequence=updated_sequence,
        damage=pending.damage_application,
        saving_throw=None,
        saving_throw_payload=pending.saving_throw_payload,
        feel_no_pain=pending.feel_no_pain,
        destroyed_model_placement=pending.destroyed_model_placement,
        destruction_attribution=ModelDestructionAttribution.for_attack(
            destroying_player_id=updated_sequence.attacker_player_id,
            attacking_unit_instance_id=updated_sequence.attacking_unit_instance_id,
            attacking_model_instance_id=pending.attack_pool.attacker_model_instance_id,
            weapon_profile=pending.attack_pool.weapon_profile,
            attack_context_id=pending.attack_context["attack_context_id"],
        ),
    )
    if destroyed_emission is None:
        raise GameLifecycleError("Deferred attack destruction did not emit evidence.")
    reaction_status = _destruction_reaction_status_if_needed(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=updated_sequence,
        attack_context=pending.attack_context,
        destruction_provenance=DestructionProvenance.for_attack(
            weapon_profile=pending.attack_pool.weapon_profile,
            attack_context_id=pending.attack_context["attack_context_id"],
        ),
        damage=pending.damage_application,
        destroyed_emission=destroyed_emission,
        destroyed_model_controller_player_id=(pending.destroyed_model_controller_player_id),
        sources=pending.destruction_sources,
    )
    if reaction_status is not None:
        return updated_sequence, reaction_status
    return updated_sequence.without_current_pending_attack_destruction(), None


def _validate_retained_model_placement(
    *,
    state: GameState,
    pending: PendingAttackDestruction,
) -> None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Deferred attack destruction requires battlefield state.")
    recorded = ModelPlacement.from_payload(
        cast(ModelPlacementPayload, pending.destroyed_model_placement)
    )
    current = battlefield.model_placement_or_none(pending.damage_application.model_instance_id)
    if current != recorded:
        raise GameLifecycleError("Deferred attack destruction placement drift.")


__all__ = (
    "CORE_DESTROYED_TIMING_RULE_ID",
    "attack_destruction_requires_end_of_attacks_boundary",
    "complete_current_attack_destruction_or_advance",
    "defer_attack_destruction_until_attacks_resolved",
    "defer_destroyed_attack_damage_if_required",
    "pending_attack_destruction_damage_event",
    "resolve_pending_attack_destruction_until_blocked",
)
