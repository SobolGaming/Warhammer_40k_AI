from __future__ import annotations

from warhammer40k_core.engine.battle_formation_hooks import (
    BattleFormationRequestContext,
    BattleFormationRequestHandler,
    BattleFormationResultContext,
    BattleFormationResultHandler,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.generic_rule_ability_registry import (
    GenericRuleAbilitySource,
    GenericRuleBattleFormationAbility,
    GenericRuleSaveOptionModifierAbility,
    GenericRuleStratagemCostChoiceAbility,
    GenericRuleStratagemCostModifierAbility,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    SaveOptionModifierContext,
    SaveOptionModifierHandler,
)
from warhammer40k_core.engine.saves import SaveOption
from warhammer40k_core.engine.stratagem_cost_choice_hooks import (
    StratagemCostChoiceRequestContext,
    StratagemCostChoiceRequestHandler,
    StratagemCostChoiceResultContext,
    StratagemCostChoiceResultHandler,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import (
    StratagemCostModifierContext,
    StratagemCostModifierHandler,
)


def battle_formation_request_handler_for_descriptor(
    source: GenericRuleAbilitySource,
    descriptor: GenericRuleBattleFormationAbility,
) -> BattleFormationRequestHandler:
    def handler(context: BattleFormationRequestContext) -> DecisionRequest | None:
        if type(context) is not BattleFormationRequestContext:
            raise GameLifecycleError("Generic RuleIR battle-formation request requires context.")
        request = descriptor.request_builder(context, source)
        if request is not None and type(request) is not DecisionRequest:
            raise GameLifecycleError(
                "Generic RuleIR battle-formation request builder must return "
                "DecisionRequest or None."
            )
        return request

    return handler


def battle_formation_result_handler_for_descriptor(
    source: GenericRuleAbilitySource,
    descriptor: GenericRuleBattleFormationAbility,
) -> BattleFormationResultHandler:
    def handler(context: BattleFormationResultContext) -> bool:
        if type(context) is not BattleFormationResultContext:
            raise GameLifecycleError("Generic RuleIR battle-formation result requires context.")
        handled = descriptor.result_builder(context, source)
        if type(handled) is not bool:
            raise GameLifecycleError(
                "Generic RuleIR battle-formation result builder must return bool."
            )
        return handled

    return handler


def stratagem_cost_choice_request_handler_for_descriptor(
    source: GenericRuleAbilitySource,
    descriptor: GenericRuleStratagemCostChoiceAbility,
) -> StratagemCostChoiceRequestHandler:
    def handler(context: StratagemCostChoiceRequestContext) -> DecisionRequest | None:
        if type(context) is not StratagemCostChoiceRequestContext:
            raise GameLifecycleError(
                "Generic RuleIR stratagem cost choice request requires context."
            )
        request = descriptor.request_builder(context, source)
        if request is not None and type(request) is not DecisionRequest:
            raise GameLifecycleError(
                "Generic RuleIR stratagem cost choice request builder must return "
                "DecisionRequest or None."
            )
        return request

    return handler


def stratagem_cost_choice_result_handler_for_descriptor(
    source: GenericRuleAbilitySource,
    descriptor: GenericRuleStratagemCostChoiceAbility,
) -> StratagemCostChoiceResultHandler:
    def handler(context: StratagemCostChoiceResultContext) -> bool:
        if type(context) is not StratagemCostChoiceResultContext:
            raise GameLifecycleError(
                "Generic RuleIR stratagem cost choice result requires context."
            )
        handled = descriptor.result_builder(context, source)
        if type(handled) is not bool:
            raise GameLifecycleError(
                "Generic RuleIR stratagem cost choice result builder must return bool."
            )
        return handled

    return handler


def stratagem_cost_modifier_handler_for_descriptor(
    source: GenericRuleAbilitySource,
    descriptor: GenericRuleStratagemCostModifierAbility,
) -> StratagemCostModifierHandler:
    def handler(context: StratagemCostModifierContext) -> int:
        if type(context) is not StratagemCostModifierContext:
            raise GameLifecycleError("Generic RuleIR stratagem cost modifier requires context.")
        if not descriptor.context_predicate(context, source):
            return context.current_command_point_cost
        modified = descriptor.modifier_builder(context, source)
        if type(modified) is not int:
            raise GameLifecycleError("Generic RuleIR stratagem cost modifier must return int.")
        return modified

    return handler


def save_option_modifier_handler_for_descriptor(
    source: GenericRuleAbilitySource,
    descriptor: GenericRuleSaveOptionModifierAbility,
) -> SaveOptionModifierHandler:
    def handler(context: SaveOptionModifierContext) -> tuple[SaveOption, ...]:
        if type(context) is not SaveOptionModifierContext:
            raise GameLifecycleError("Generic RuleIR save option modifier requires context.")
        if not descriptor.context_predicate(context, source):
            return context.save_options
        modified = descriptor.modifier_builder(context, source)
        if type(modified) is not tuple:
            raise GameLifecycleError("Generic RuleIR save option modifier must return a tuple.")
        return modified

    return handler
