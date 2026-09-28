from __future__ import annotations

from functools import partial

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.modifiers import RollModifier, resolve_roll_modifiers
from warhammer40k_core.engine.army_mustering import ArmyDefinition, EnhancementAssignment
from warhammer40k_core.engine.attack_completion_sequencing import (
    resolve_attack_completion_candidates,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import AttackSequenceCompletedContext
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.modifier_evaluation import ModifierEvaluationSubject, select_modifiers
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.unit_factory import UnitInstance

from . import enhancements as _enhancements


def candidates(context: AttackSequenceCompletedContext) -> tuple[TimingRuleCandidate, ...]:
    if context.source_phase is not BattlePhase.FIGHT:
        return ()
    entries: list[TimingRuleCandidate] = []
    for army, assignment, bearer in _enhancements.assigned_soulstealer_bearers(context.state):
        _enhancements.validate_daemonic_incursion_bearer(
            army=army,
            unit=bearer,
            required_keyword="SLAANESH",
            rule_label="Soulstealer",
        )
        for event_id, payload in _enhancements.destroyed_enemy_model_events_for_sequence(
            context=context,
            army=army,
            bearer=bearer,
            bearer_model_ids=frozenset(model.model_instance_id for model in bearer.own_models),
        ):
            if _enhancements.soulstealer_event_already_resolved(
                context=context, destroyed_model_event_id=event_id
            ):
                continue
            entries.append(
                TimingRuleCandidate(
                    participant=SequencingParticipant(
                        participant_id=f"soulstealer:{bearer.unit_instance_id}:{event_id}",
                        source_rule_id=_enhancements.SOULSTEALER_SOURCE_RULE_ID,
                        player_id=army.player_id,
                        requirement=SequencingRequirement.MANDATORY,
                        payload={
                            "destroyed_model_event_id": event_id,
                            "source_unit_instance_id": bearer.unit_instance_id,
                        },
                    ),
                    activate=partial(
                        _activate, context, army, assignment, bearer, event_id, payload
                    ),
                )
            )
    return tuple(entries)


def resolve(context: AttackSequenceCompletedContext) -> LifecycleStatus | None:
    return resolve_attack_completion_candidates(context, partial(candidates, context))


def _activate(
    context: AttackSequenceCompletedContext,
    army: ArmyDefinition,
    assignment: EnhancementAssignment,
    bearer: UnitInstance,
    event_id: str,
    payload: dict[str, JsonValue],
) -> LifecycleStatus | None:
    bearer_model_id = _enhancements.payload_identifier(payload, "attacking_model_instance_id")
    shadow_bonus = (
        1 if _enhancements.bearer_within_shadow(context.state, army=army, bearer=bearer) else 0
    )
    subject_unit = rules_unit_view_by_id(
        state=context.state, unit_instance_id=bearer.unit_instance_id
    )
    selected = select_modifiers(
        state=context.state,
        decisions=context.decisions,
        ability_index=context.runtime_modifier_registry.modifier_permission_index(army.player_id),
        occurrence_id=f"soulstealer:{context.attack_sequence.sequence_id}:{event_id}",
        subject=ModifierEvaluationSubject(
            unit_instance_id=subject_unit.unit_instance_id,
            model_instance_id=bearer_model_id,
            kind=ModifierIgnoreKind.HEALING_ROLL,
        ),
        modifiers=(
            (
                RollModifier(
                    modifier_id=f"{_enhancements.SOULSTEALER_SOURCE_RULE_ID}:shadow-bonus",
                    source_id=_enhancements.SOULSTEALER_SOURCE_RULE_ID,
                    operand=shadow_bonus,
                ),
            )
            if shadow_bonus
            else ()
        ),
        source_context={
            "owner": "attack_completion",
            "sequence_id": context.attack_sequence.sequence_id,
            "attack_sequence_completed_event_id": context.attack_sequence_completed_event_id,
            "destroyed_model_event_id": event_id,
            "source_rule_id": _enhancements.SOULSTEALER_SOURCE_RULE_ID,
        },
    )
    if selected.pending_status is not None:
        return selected.pending_status
    d6_result = context.dice_manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="Soulstealer",
            roll_type=_enhancements.SOULSTEALER_D6_ROLL_TYPE,
            actor_id=bearer_model_id,
        )
    )
    roll_total = resolve_roll_modifiers(d6_result.current_total, selected.modifiers).final
    heal_succeeded = roll_total >= 4
    before_wounds, after_wounds = _enhancements.heal_bearer_model(
        state=context.state,
        unit_instance_id=bearer.unit_instance_id,
        model_instance_id=bearer_model_id,
        amount=1 if heal_succeeded else 0,
    )
    context.decisions.event_log.append(
        _enhancements.SOULSTEALER_RESOLVED_EVENT,
        _enhancements.soulstealer_resolution_payload(
            context=context,
            army=army,
            assignment=assignment,
            bearer=bearer,
            destroyed_model_event_id=event_id,
            destroyed_model_payload=payload,
            bearer_model_id=bearer_model_id,
            d6_result=validate_json_value(d6_result.to_payload()),
            shadow_bonus=shadow_bonus,
            roll_total=roll_total,
            heal_succeeded=heal_succeeded,
            before_wounds=before_wounds,
            after_wounds=after_wounds,
        ),
    )
    return None
