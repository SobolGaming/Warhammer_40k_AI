from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDurationKind,
    RuleEffectKind,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID = "catalog-ir:command-phase-ability-mode"
COMMAND_PHASE_ABILITY_MODE_TEMPLATE_ID = "phase17k:command-phase-self-ability-choice"
SELECTABLE_ABILITY_MODE_OPTION_TEMPLATE_ID = "phase17k:selectable-self-ability-option"

BEGUILING_FORM_MODE_SEMANTIC = "defensive_hit_roll_modifier"
DAEMONIC_SPEED_MODE_SEMANTIC = "fights_first"
ENTHRALLING_HYPNOSIS_MODE_SEMANTIC = "fall_back_leadership_denial_aura"


@dataclass(frozen=True, slots=True)
class SelectableAbilityModeOptionDescriptor:
    semantic: str
    hit_roll_delta: int | None = None
    aura_range_inches: float | None = None


def clause_is_command_phase_ability_mode_choice(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Selectable ability mode classifier requires RuleClause.")
    trigger = clause.trigger
    target = clause.target
    duration = clause.duration
    if (
        not clause.is_supported
        or clause.template_id != COMMAND_PHASE_ABILITY_MODE_TEMPLATE_ID
        or trigger is None
        or trigger.kind is not RuleTriggerKind.TIMING_WINDOW
        or target is None
        or target.kind is not RuleTargetKind.THIS_MODEL
        or duration is None
        or duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or clause.conditions
        or len(clause.effects) != 1
    ):
        return False
    trigger_parameters = parameter_payload(trigger.parameters)
    duration_parameters = parameter_payload(duration.parameters)
    effect = clause.effects[0]
    effect_parameters = parameter_payload(effect.parameters)
    option_ids = effect_parameters.get("option_source_rule_ids")
    return (
        trigger_parameters
        == {
            "edge": "start",
            "owner": "opponent",
            "phase": "command",
            "subject": "this_model",
            "timing_window": "start_opponents_command_phase",
        }
        and duration_parameters
        == {
            "battle_round_offset": 1,
            "boundary": "start",
            "endpoint": "phase",
            "owner": "opponent",
            "phase": "command",
        }
        and effect.kind is RuleEffectKind.GRANT_ABILITY
        and set(effect_parameters) == {"ability", "option_source_rule_ids"}
        and effect_parameters.get("ability") == "select_one_self_ability_mode"
        and type(option_ids) is tuple
        and len(option_ids) >= 2
        and all(type(value) is str and value for value in option_ids)
        and len(set(option_ids)) == len(option_ids)
    )


def selectable_ability_mode_option_descriptor(
    clause: RuleClause,
) -> SelectableAbilityModeOptionDescriptor | None:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Selectable ability mode option requires RuleClause.")
    if (
        not clause.is_supported
        or clause.template_id != SELECTABLE_ABILITY_MODE_OPTION_TEMPLATE_ID
        or clause.trigger is not None
        or clause.conditions
        or clause.duration is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or len(clause.effects) != 1
    ):
        return None
    effect = clause.effects[0]
    parameters = parameter_payload(effect.parameters)
    hit_roll_delta = parameters.get("delta")
    if (
        effect.kind is RuleEffectKind.MODIFY_DICE_ROLL
        and set(parameters) == {"attack_role", "delta", "roll_type"}
        and parameters.get("attack_role") == "target"
        and parameters.get("roll_type") == "hit"
        and type(hit_roll_delta) is int
        and hit_roll_delta < 0
    ):
        return SelectableAbilityModeOptionDescriptor(
            semantic=BEGUILING_FORM_MODE_SEMANTIC,
            hit_roll_delta=hit_roll_delta,
        )
    if effect.kind is RuleEffectKind.GRANT_ABILITY and parameters == {"ability": "fights_first"}:
        return SelectableAbilityModeOptionDescriptor(semantic=DAEMONIC_SPEED_MODE_SEMANTIC)
    aura_range_inches = parameters.get("aura_range_inches")
    if (
        effect.kind is RuleEffectKind.SET_CONTEXTUAL_STATUS
        and set(parameters)
        == {
            "aura_range_inches",
            "failure_effect",
            "status",
            "test_characteristic",
        }
        and parameters.get("status") == "fall_back_leadership_test_denial"
        and parameters.get("test_characteristic") == "leadership"
        and parameters.get("failure_effect") == "remain_stationary"
        and isinstance(aura_range_inches, int | float)
        and type(aura_range_inches) is not bool
        and float(aura_range_inches) > 0.0
    ):
        return SelectableAbilityModeOptionDescriptor(
            semantic=ENTHRALLING_HYPNOSIS_MODE_SEMANTIC,
            aura_range_inches=float(aura_range_inches),
        )
    return None


def consumer_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    if clause_is_command_phase_ability_mode_choice(clause):
        return (CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID,)
    if selectable_ability_mode_option_descriptor(clause) is not None:
        return (CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID,)
    return ()


def registered_consumer_ids() -> tuple[str, ...]:
    return (CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID,)
