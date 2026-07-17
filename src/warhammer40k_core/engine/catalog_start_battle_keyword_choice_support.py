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

CATALOG_IR_START_BATTLE_KEYWORD_CHOICE_CONSUMER_ID = "catalog-ir:start-battle-keyword-choice"
START_BATTLE_KEYWORD_CHOICE_TEMPLATE_ID = "phase17c:start-battle-keyword-choice-reroll"


@dataclass(frozen=True, slots=True)
class CatalogStartBattleKeywordChoiceDescriptor:
    keyword_options: tuple[str, ...]


def start_battle_keyword_choice_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogStartBattleKeywordChoiceDescriptor | None:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog keyword choice classification requires RuleClause.")
    if (
        not clause.is_supported
        or clause.template_id != START_BATTLE_KEYWORD_CHOICE_TEMPLATE_ID
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or clause.target.parameters
        or clause.conditions
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.PERMANENT
        or len(clause.effects) != 2
    ):
        return None
    trigger = parameter_payload(clause.trigger.parameters)
    keyword_options = trigger.get("keyword_options")
    if (
        trigger.get("edge") != "start"
        or trigger.get("phase") != "battle"
        or trigger.get("subject") != "this_model"
        or trigger.get("timing_window") != "start_battle"
        or type(keyword_options) is not tuple
        or not keyword_options
        or tuple(sorted(set(keyword_options))) != tuple(sorted(keyword_options))
        or not all(
            type(keyword) is str and keyword and keyword == keyword.upper()
            for keyword in keyword_options
        )
    ):
        return None
    expected_roll_types = ("hit", "wound")
    for effect, roll_type in zip(clause.effects, expected_roll_types, strict=True):
        parameters = parameter_payload(effect.parameters)
        if effect.kind is not RuleEffectKind.REROLL_PERMISSION or parameters != {
            "attack_role": "attacker",
            "reroll_unmodified_value": 1,
            "roll_type": roll_type,
            "target_required_keyword": "selected_keyword",
            "timing_window": f"attack_sequence.{roll_type}",
        }:
            return None
    return CatalogStartBattleKeywordChoiceDescriptor(keyword_options=keyword_options)


def clause_is_start_battle_keyword_choice(clause: RuleClause) -> bool:
    return start_battle_keyword_choice_descriptor_for_clause(clause) is not None


def clause_has_invalid_exact_start_battle_keyword_choice_shape(clause: RuleClause) -> bool:
    return (
        clause.template_id == START_BATTLE_KEYWORD_CHOICE_TEMPLATE_ID
        and start_battle_keyword_choice_descriptor_for_clause(clause) is None
    )
