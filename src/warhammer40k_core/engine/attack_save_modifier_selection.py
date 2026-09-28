"""Prepare and retain model-specific saves before grouped dice and allocation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.modifiers import Modifier, RollModifier
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.modifier_evaluation import (
    ModifierEvaluationSubject,
    select_modifiers,
    selected_modifiers_for_occurrence,
    selection_history,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.save_modifier_operations import save_option_ignoring_modifiers
from warhammer40k_core.engine.saves import SaveKind, SaveOption, SaveOptionPayload

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_model import AttackResolutionContextPayload
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

SAVE_MODIFIER_SNAPSHOT_EVENT = "attack_save_modifiers_prepared"


@dataclass(frozen=True, slots=True)
class SaveModifierEvaluation:
    occurrence_id: str
    subject: ModifierEvaluationSubject
    modifiers: tuple[Modifier, ...] | tuple[RollModifier, ...]


def save_modifier_evaluations(
    *,
    options: tuple[SaveOption, ...],
    attack_context: AttackResolutionContextPayload,
    model_id: str,
    rolls: bool,
) -> tuple[SaveModifierEvaluation, ...]:
    context_id = attack_context["attack_context_id"]
    prefix = f"{context_id}:save:{model_id}"
    values: list[SaveModifierEvaluation] = []
    for option in options:
        if not rolls and option.characteristic_trace is not None:
            values.append(
                SaveModifierEvaluation(
                    f"{prefix}:{option.save_kind.value}:characteristic",
                    ModifierEvaluationSubject(
                        attack_context["target_unit_instance_id"],
                        (
                            ModifierIgnoreKind.SAVE_CHARACTERISTIC
                            if option.save_kind is SaveKind.ARMOUR
                            else ModifierIgnoreKind.INVULNERABLE_SAVE_CHARACTERISTIC
                        ),
                        model_instance_id=model_id,
                    ),
                    option.characteristic_trace.modifiers,
                )
            )
        if not rolls and option.armor_penetration_trace is not None:
            values.append(
                SaveModifierEvaluation(
                    f"{prefix}:armor-penetration",
                    ModifierEvaluationSubject(
                        attack_context["attacking_unit_instance_id"],
                        ModifierIgnoreKind.ARMOR_PENETRATION_CHARACTERISTIC,
                        model_instance_id=attack_context["attacker_model_instance_id"],
                        weapon_profile_id=attack_context["weapon_profile_id"],
                    ),
                    option.armor_penetration_trace.modifiers,
                )
            )
        roll_operations = (
            *option.roll_modifiers,
            *(modifier for modifier in option.inherent_roll_modifiers if modifier.operand != 0),
        )
        if rolls and roll_operations:
            values.append(
                SaveModifierEvaluation(
                    f"{prefix}:{option.save_kind.value}:roll",
                    ModifierEvaluationSubject(
                        attack_context["target_unit_instance_id"],
                        ModifierIgnoreKind.SAVE_ROLL,
                        model_instance_id=model_id,
                    ),
                    roll_operations,
                )
            )
    return tuple(values)


def prepare_attack_save_modifiers(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
    sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    model_id: str,
    options: tuple[SaveOption, ...],
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    if (
        retained_attack_save_options(
            decisions=decisions,
            attack_context=attack_context,
            model_id=model_id,
        )
        is not None
    ):
        return None
    has_choices = False
    current_options = options
    for rolls in (False, True):
        evaluations = save_modifier_evaluations(
            options=current_options,
            attack_context=attack_context,
            model_id=model_id,
            rolls=rolls,
        )
        for evaluation in evaluations:
            owner = rules_unit_view_by_id(
                state=state, unit_instance_id=evaluation.subject.unit_instance_id
            )
            selected = select_modifiers(
                state=state,
                decisions=decisions,
                ability_index=runtime_modifier_registry.modifier_permission_index(
                    owner.owner_player_id
                ),
                occurrence_id=evaluation.occurrence_id,
                subject=evaluation.subject,
                modifiers=evaluation.modifiers,
                source_context={
                    "continuation": "attack",
                    "evaluation_stage": "save",
                    "sequence_id": sequence.sequence_id,
                    "attack_context_id": attack_context["attack_context_id"],
                    "source_phase": sequence.source_phase.value,
                    "allocated_model_instance_id": model_id,
                },
            )
            if selected.pending_status is not None:
                return selected.pending_status
            has_choices = (
                has_choices
                or selection_history(
                    decision_records=decisions.records,
                    occurrence_id=evaluation.occurrence_id,
                    subject=evaluation.subject,
                )
                is not None
            )
        if not rolls:
            current_options = _selected_options(
                decisions=decisions,
                options=options,
                attack_context=attack_context,
                model_id=model_id,
                include_rolls=False,
            )
    if has_choices:
        chosen = _selected_options(
            decisions=decisions,
            options=options,
            attack_context=attack_context,
            model_id=model_id,
        )
        decisions.event_log.append(
            SAVE_MODIFIER_SNAPSHOT_EVENT,
            validate_json_value(
                {
                    "sequence_id": sequence.sequence_id,
                    "attack_context": attack_context,
                    "model_instance_id": model_id,
                    "source_options": [option.to_payload() for option in options],
                    "selected_options": [option.to_payload() for option in chosen],
                }
            ),
        )
    return None


def retained_attack_save_options(
    *,
    decisions: DecisionController,
    attack_context: AttackResolutionContextPayload,
    model_id: str,
) -> tuple[SaveOption, ...] | None:
    matches: list[dict[str, JsonValue]] = []
    for event in decisions.event_log.records:
        row = event.payload
        if event.event_type != SAVE_MODIFIER_SNAPSHOT_EVENT or not isinstance(row, dict):
            continue
        context = row.get("attack_context")
        if (
            isinstance(context, dict)
            and context.get("attack_context_id") == attack_context["attack_context_id"]
            and row.get("model_instance_id") == model_id
        ):
            matches.append(row)
    if not matches:
        return None
    if len(matches) != 1:
        raise GameLifecycleError("Save modifier snapshot occurrence is duplicated.")
    row = matches[0]
    if set(row) != {
        "sequence_id",
        "attack_context",
        "model_instance_id",
        "source_options",
        "selected_options",
    }:
        raise GameLifecycleError("Save modifier snapshot fields drifted.")
    if canonical_json(row["attack_context"]) != canonical_json(validate_json_value(attack_context)):
        raise GameLifecycleError("Save modifier snapshot attack context drifted.")
    source = _options(row["source_options"])
    chosen = _selected_options(
        decisions=decisions,
        options=source,
        attack_context=attack_context,
        model_id=model_id,
    )
    if chosen != _options(row["selected_options"]):
        raise GameLifecycleError("Save modifier snapshot differs from its recorded choices.")
    if not any(
        selection_history(
            decision_records=decisions.records,
            occurrence_id=evaluation.occurrence_id,
            subject=evaluation.subject,
        )
        is not None
        for rolls in (False, True)
        for evaluation in save_modifier_evaluations(
            options=source,
            attack_context=attack_context,
            model_id=model_id,
            rolls=rolls,
        )
    ):
        raise GameLifecycleError("Save modifier snapshot lacks its source choices.")
    return chosen


def _selected_options(
    *,
    decisions: DecisionController,
    options: tuple[SaveOption, ...],
    attack_context: AttackResolutionContextPayload,
    model_id: str,
    include_rolls: bool = True,
) -> tuple[SaveOption, ...]:
    result: list[SaveOption] = []
    for option in options:
        ignored: list[str] = []
        for rolls in (False, True) if include_rolls else (False,):
            for evaluation in save_modifier_evaluations(
                options=(option,),
                attack_context=attack_context,
                model_id=model_id,
                rolls=rolls,
            ):
                selected = selected_modifiers_for_occurrence(
                    decision_records=decisions.records,
                    occurrence_id=evaluation.occurrence_id,
                    subject=evaluation.subject,
                    modifiers=evaluation.modifiers,
                )
                selected_ids = {modifier.modifier_id for modifier in selected}
                ignored.extend(
                    modifier.modifier_id
                    for modifier in evaluation.modifiers
                    if modifier.modifier_id not in selected_ids
                )
            option = save_option_ignoring_modifiers(option, tuple(ignored))
        result.append(option)
    return tuple(result)


def _options(value: JsonValue) -> tuple[SaveOption, ...]:
    if not isinstance(value, list) or any(not isinstance(option, dict) for option in value):
        raise GameLifecycleError("Save modifier snapshot options require objects.")
    return tuple(SaveOption.from_payload(cast(SaveOptionPayload, option)) for option in value)
