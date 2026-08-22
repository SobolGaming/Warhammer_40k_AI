from __future__ import annotations

from warhammer40k_core.engine.battle_formation_hooks import (
    BattleFormationRequestContext,
    BattleFormationRequestHandler,
    BattleFormationResultContext,
    BattleFormationResultHandler,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantHandler,
)
from warhammer40k_core.engine.generic_rule_ability_effects import (
    generic_rule_ability_effects_for_unit,
)
from warhammer40k_core.engine.generic_rule_ability_registry import (
    GenericRuleAbilitySource,
    GenericRuleBattleFormationAbility,
    GenericRuleFightUnitSelectedGrantAbility,
    GenericRuleSaveOptionModifierAbility,
    GenericRuleStratagemCostChoiceAbility,
    GenericRuleStratagemCostModifierAbility,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
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
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
)


def fight_unit_selected_grant_handler_for_descriptor(
    source: GenericRuleAbilitySource,
    descriptor: GenericRuleFightUnitSelectedGrantAbility,
) -> FightUnitSelectedGrantHandler:
    def handler(context: FightUnitSelectedContext) -> FightUnitSelectedGrant | None:
        if type(context) is not FightUnitSelectedContext:
            raise GameLifecycleError("Generic RuleIR fight grant ability requires context.")
        matching_effects = generic_rule_ability_effects_for_unit(
            state=context.state,
            source=source,
            unit_instance_id=descriptor.target_unit_instance_id(context),
            ability=descriptor.ability_id,
        )
        if not matching_effects and not _enhancement_is_assigned_to_selected_rules_unit(
            context=context,
            source=source,
        ):
            return None
        if not descriptor.context_predicate(context, source, matching_effects):
            return None
        return descriptor.grant_builder(context, source, matching_effects)

    return handler


def _enhancement_is_assigned_to_selected_rules_unit(
    *,
    context: FightUnitSelectedContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if (
        source.record.coverage_kind
        is not faction_coverage_2026_27.Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
    ):
        return False
    enhancement_id = source.record.rule_id
    if enhancement_id is None:
        raise GameLifecycleError("Generic enhancement fight grant requires rule_id.")
    army = context.state.army_definition_for_player(context.player_id)
    if army is None:
        raise GameLifecycleError("Generic enhancement fight grant requires player army.")
    selected_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
    )
    if selected_rules_unit.owner_player_id != context.player_id:
        raise GameLifecycleError("Generic enhancement fight grant owner drift.")
    selected_component_ids = set(selected_rules_unit.component_unit_instance_ids)
    for assignment in army.enhancement_assignments:
        if assignment.enhancement_id != enhancement_id:
            continue
        bearer_unit_id = f"{army.army_id}:{assignment.target_unit_selection_id}"
        if bearer_unit_id in selected_component_ids:
            return True
    return False


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
