from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)


def clause_is_post_shoot_hit_target_status_denial(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    trigger = parameter_payload(clause.trigger.parameters)
    if (
        trigger.get("edge") != "after"
        or trigger.get("owner") != "active_player"
        or trigger.get("phase") != BattlePhase.SHOOTING.value
        or trigger.get("timing_window") != "just_after_friendly_unit_has_shot"
        or trigger.get("target_relationship") != "hit_by_those_attacks"
        or trigger.get("subject") not in {"this_model", "this_unit", "bearer"}
        or not _optional_weapon_names_are_well_formed(trigger.get("weapon_names"))
    ):
        return False
    if (
        clause.duration is None
        or clause.duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or parameter_payload(clause.duration.parameters).get("endpoint") != "phase"
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.ENEMY_UNIT
    ):
        return False
    return sum(1 for effect in clause.effects if effect_is_status_denial(effect)) == 1


def effect_is_status_denial(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("rules_context") == "status_denial"
        and parameters.get("operation") == "deny"
        and parameters.get("status") == "benefit_of_cover"
        and parameters.get("target_scope") in {"selected_unit", "models_in_selected_unit"}
    )


def _optional_weapon_names_are_well_formed(value: object) -> bool:
    if value is None:
        return True
    if type(value) is not tuple or not value:
        return False
    return all(type(name) is str and bool(name.strip()) for name in cast(tuple[object, ...], value))
